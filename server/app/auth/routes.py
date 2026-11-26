"""로그인 API. 계약은 docs/auth-plan.md 참고.

  POST   /api/auth/{provider}            모바일: 카카오 access token / 구글 ID token → 우리 토큰
  GET    /api/auth/{provider}/authorize  서버 흐름 시작 (state + PKCE) → 제공자로 302
  GET    /api/auth/{provider}/callback   제공자 → 앱 딥링크로 302 (1회용 코드)
  POST   /api/auth/token                 1회용 코드 + code_verifier → 우리 토큰
  POST   /api/auth/refresh               refresh 회전
  POST   /api/auth/logout                세션 끊기
  DELETE /api/me                         탈퇴
  GET    /api/me                         내 정보
  POST   /api/me/push-token              푸시 토큰 등록
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session, utcnow
from ..family.service import on_user_withdrawn
from . import redirect, service
from .config import AuthSettings, get_settings
from .deps import AuthContext, client_meta, current_auth, optional_auth, providers_dep, settings_dep
from .errors import MSG_LOGIN_FAILED, AuthError, auth_error_handler
from .providers import Providers

log = logging.getLogger("ilgeodeurim.auth")

router = APIRouter()
ProviderName = Literal["kakao", "google", "fake"]
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class DeviceFields(BaseModel):
    deviceId: str | None = Field(default=None, max_length=100)
    deviceOs: Literal["ANDROID", "IOS", "WEB", "android", "ios", "web"] | None = None


class SocialLoginBody(DeviceFields):
    accessToken: str | None = Field(default=None, max_length=4096)
    idToken: str | None = Field(default=None, max_length=8192)
    userType: Literal["SENIOR", "CHILD"] | None = None


class TokenBody(DeviceFields):
    grantType: Literal["authorization_code"] = "authorization_code"
    code: str = Field(max_length=200)
    codeVerifier: str = Field(max_length=128)
    redirectUri: str = Field(max_length=500)


class RefreshBody(DeviceFields):
    refreshToken: str = Field(max_length=200)


class LogoutBody(DeviceFields):
    refreshToken: str | None = Field(default=None, max_length=200)
    allDevices: bool = False


class WithdrawBody(BaseModel):
    kakaoAccessToken: str | None = Field(default=None, max_length=4096)


class PushTokenBody(BaseModel):
    pushToken: str = Field(min_length=1, max_length=500)
    platform: Literal["ANDROID", "IOS", "WEB", "android", "ios", "web"]
    deviceId: str | None = Field(default=None, max_length=100)


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def user_json(user, providers: list[str]) -> dict:
    return {
        "userNo": user.user_no,
        "userType": user.user_type_cd,
        "name": user.name,
        "email": user.email,
        "profileImageUrl": user.profile_image_url,
        "providers": providers,
    }


def token_response(t: service.IssuedTokens, *, include_new_user: bool = True) -> JSONResponse:
    now: datetime = utcnow()
    body = {
        "tokenType": "Bearer",
        "accessToken": t.access_token,
        "accessTokenExpiresIn": max(0, int((t.access_expires_at - now).total_seconds())),
        "refreshToken": t.refresh_token,
        "refreshTokenExpiresIn": max(0, int((t.refresh_expires_at - now).total_seconds())),
        "user": user_json(t.user, t.providers),
    }
    if include_new_user:
        body["isNewUser"] = t.is_new_user
    return JSONResponse(body, headers=NO_STORE)


# 고정 경로를 {provider} 보다 먼저 둔다.

@router.post("/api/auth/token")
async def exchange_token(request: Request, body: TokenBody, db: AsyncSession = Depends(get_session),
                         s: AuthSettings = Depends(settings_dep)):
    meta = client_meta(request, body.deviceId, body.deviceOs)
    t = await service.exchange_login_code(db, s, code=body.code, code_verifier=body.codeVerifier,
                                          redirect_uri=body.redirectUri, meta=meta)
    return token_response(t)


@router.post("/api/auth/refresh")
async def refresh(request: Request, body: RefreshBody, db: AsyncSession = Depends(get_session),
                  s: AuthSettings = Depends(settings_dep)):
    meta = client_meta(request, body.deviceId, body.deviceOs)
    t = await service.rotate_refresh(db, s, body.refreshToken, meta)
    return token_response(t, include_new_user=False)


@router.post("/api/auth/logout", status_code=204)
async def logout(request: Request, body: LogoutBody | None = Body(default=None),
                 db: AsyncSession = Depends(get_session), auth: AuthContext | None = Depends(optional_auth)):
    body = body or LogoutBody()
    meta = client_meta(request, body.deviceId, body.deviceOs)
    await service.logout(db, refresh_token=body.refreshToken, claims=auth.claims if auth else None,
                         all_devices=body.allDevices, meta=meta)
    return Response(status_code=204)


@router.delete("/api/me")
async def withdraw(request: Request, body: WithdrawBody | None = Body(default=None),
                   auth: AuthContext = Depends(current_auth), db: AsyncSession = Depends(get_session),
                   providers: Providers = Depends(providers_dep)):
    # current_auth 와 같은 요청 안에서는 get_session 이 같은 세션이라 auth.user 를 그대로 고친다.
    results = await service.withdraw(db, providers, auth.user,
                                     kakao_access_token=body.kakaoAccessToken if body else None,
                                     meta=client_meta(request))
    # 가족 연결 끊기·내 서류 지우기. 실패해도 권한 검사가 탈퇴 회원을 막는다(두 번째 방어).
    await on_user_withdrawn(db, auth.user.user_no)
    return JSONResponse({"ok": True, "unlinked": results}, headers=NO_STORE)


@router.get("/api/me")
async def me(auth: AuthContext = Depends(current_auth), db: AsyncSession = Depends(get_session)):
    body = user_json(auth.user, await service.providers_of(db, auth.user.user_no))
    body["createdAt"] = _iso_utc(auth.user.created_at)
    return JSONResponse(body, headers=NO_STORE)


@router.post("/api/me/push-token", status_code=204)
async def push_token(body: PushTokenBody, auth: AuthContext = Depends(current_auth),
                     db: AsyncSession = Depends(get_session)):
    await service.register_push_token(
        db, auth.user.user_no, push_token=body.pushToken, platform=body.platform, device_id=body.deviceId)
    return Response(status_code=204)


@router.post("/api/auth/{provider}")
async def social_login(provider: ProviderName, request: Request, body: SocialLoginBody,
                       db: AsyncSession = Depends(get_session), providers: Providers = Depends(providers_dep),
                       s: AuthSettings = Depends(settings_dep)):
    meta = client_meta(request, body.deviceId, body.deviceOs)
    client = providers.get(provider)
    try:
        if provider == "kakao":
            profile = await client.verify_access_token(body.accessToken)
        elif provider == "google":
            profile = await client.verify_id_token(body.idToken)
        else:
            profile = client.verify_access_token(body.accessToken)
    except AuthError as e:
        log.info("social login rejected provider=%s reason=%s", provider, e.code)
        await service.log_failure(db, "LOGIN_FAIL", meta, provider=provider.upper(), reason=e.code)
        raise
    t = await service.login_with_profile(db, s, profile, user_type=body.userType, meta=meta)
    return token_response(t)


@router.get("/api/auth/{provider}/authorize")
async def authorize(provider: ProviderName, request: Request,
                    redirect_uri: str = Query(max_length=500),
                    state: str | None = Query(default=None, max_length=200),
                    code_challenge: str | None = Query(default=None, max_length=128),
                    code_challenge_method: str | None = Query(default=None, max_length=10),
                    user_type: Literal["SENIOR", "CHILD"] | None = None,
                    device_id: str | None = Query(default=None, max_length=100),
                    login_hint: str | None = Query(default=None, max_length=64),
                    db: AsyncSession = Depends(get_session), providers: Providers = Depends(providers_dep),
                    s: AuthSettings = Depends(settings_dep)):
    if not redirect.is_allowed(s, redirect_uri):
        # 모르는 주소로는 절대 돌려보내지 않는다 (열린 리다이렉트).
        raise AuthError(400, "invalid_redirect_uri", MSG_LOGIN_FAILED)
    try:
        client = providers.get(provider)
        url = await service.begin_authorize(
            db, s, client, provider_name=provider, app_redirect_uri=redirect_uri, app_state=state,
            app_code_challenge=code_challenge, app_code_challenge_method=code_challenge_method,
            user_type=user_type, device_id=device_id, login_hint=login_hint)
    except AuthError as e:
        url = redirect.login_failed_url(redirect_uri, provider=provider, reason=e.code, message=e.user_message,
                                        app_state=state)
    return RedirectResponse(url, status_code=302, headers=NO_STORE)


@router.get("/api/auth/{provider}/callback")
async def callback(provider: ProviderName, request: Request,
                   code: str | None = Query(default=None, max_length=2048),
                   state: str | None = Query(default=None, max_length=200),
                   error: str | None = Query(default=None, max_length=200),
                   db: AsyncSession = Depends(get_session), providers: Providers = Depends(providers_dep),
                   s: AuthSettings = Depends(settings_dep)):
    try:
        client = providers.get(provider)
    except AuthError as e:
        url = redirect.login_failed_url(redirect.default_callback(s), provider=provider, reason=e.code,
                                        message=e.user_message, app_state=None)
        return RedirectResponse(url, status_code=302, headers=NO_STORE)
    url = await service.complete_callback(db, s, client, provider_name=provider, state=state, code=code,
                                          error=error, meta=client_meta(request))
    return RedirectResponse(url, status_code=302, headers=NO_STORE)


def install(app: FastAPI) -> None:
    app.add_exception_handler(AuthError, auth_error_handler)
    app.include_router(router)
    if get_settings().fake_provider:
        log.warning("AUTH_FAKE_PROVIDER=1 — 가짜 로그인이 켜져 있어요. 운영에서는 끄세요.")
