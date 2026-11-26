"""소셜 제공자 확인. 앱이 준 토큰이나 인가 코드를 제공자에게 직접 물어 회원 ID 를 얻는다.

AsOne oauth/*OAuth2UserInfo 와 같은 역할(제공자 응답 → id/이름/이메일/사진).
다른 점: 카카오 이메일을 필수로 두지 않는다(어르신은 이메일이 없는 경우가 많다). 회원은 제공자 ID 로만 찾는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from . import pkce
from .config import AuthSettings
from .errors import MSG_NOT_READY, AuthError, ProviderAuthError
from .oidc import verify_google_id_token

log = logging.getLogger("ilgeodeurim.auth")

MAX_PROVIDER_TOKEN_LEN = 4096


@dataclass(frozen=True)
class ProviderProfile:
    provider: str  # KAKAO / GOOGLE / FAKE
    oauth_id: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    picture: str | None = None


class Provider(Protocol):
    code: str

    def authorize_url(self, *, state: str, code_challenge: str, nonce: str, login_hint: str | None) -> str: ...

    async def exchange_code(self, code: str, *, code_verifier: str, nonce: str | None) -> ProviderProfile: ...

    async def unlink(self, oauth_id: str, *, user_access_token: str | None = None) -> str: ...


def _check_token(token: str | None) -> str:
    if not token or not isinstance(token, str) or len(token) > MAX_PROVIDER_TOKEN_LEN:
        raise ProviderAuthError("token_missing", 400)
    return token


def _str(v) -> str | None:
    return v if isinstance(v, str) and v.strip() else None


class KakaoProvider:
    code = "KAKAO"
    AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    TOKEN_INFO_URL = "https://kapi.kakao.com/v1/user/access_token_info"
    ME_URL = "https://kapi.kakao.com/v2/user/me"
    UNLINK_URL = "https://kapi.kakao.com/v1/user/unlink"

    def __init__(self, s: AuthSettings, http: httpx.AsyncClient):
        self.s, self.http = s, http

    async def _get(self, url: str, token: str, **params) -> dict:
        try:
            r = await self.http.get(url, headers={"Authorization": f"Bearer {token}"}, params=params or None,
                                    timeout=8.0)
        except httpx.HTTPError:
            raise ProviderAuthError("kakao_unavailable", 502) from None
        if r.status_code in (400, 401):
            raise ProviderAuthError("kakao_token_invalid")
        if r.status_code != 200:
            raise ProviderAuthError("kakao_unavailable", 502)
        try:
            return r.json()
        except ValueError:
            raise ProviderAuthError("kakao_bad_response", 502) from None

    async def verify_access_token(self, token: str | None, *, require_app_id: bool = True) -> ProviderProfile:
        """앱 SDK 가 받은 카카오 access token. 다른 앱에서 받은 토큰이면 거절한다(app_id 확인)."""
        token = _check_token(token)
        if require_app_id and not self.s.kakao_app_id:
            raise ProviderAuthError("kakao_not_configured", 503, MSG_NOT_READY)
        info = await self._get(self.TOKEN_INFO_URL, token)
        if self.s.kakao_app_id and str(info.get("app_id")) != self.s.kakao_app_id:
            raise ProviderAuthError("kakao_app_mismatch")
        me = await self._get(self.ME_URL, token, secure_resource="true")
        if me.get("id") is None or str(me.get("id")) != str(info.get("id")):
            raise ProviderAuthError("kakao_id_mismatch")
        return self.profile(me)

    @staticmethod
    def profile(me: dict) -> ProviderProfile:
        account = me.get("kakao_account") if isinstance(me.get("kakao_account"), dict) else {}
        prof = account.get("profile") if isinstance(account.get("profile"), dict) else {}
        props = me.get("properties") if isinstance(me.get("properties"), dict) else {}
        email = _str(account.get("email"))
        verified = bool(email) and account.get("is_email_valid") is True and account.get("is_email_verified") is True
        picture = None if prof.get("is_default_image") is True else (
            _str(prof.get("profile_image_url")) or _str(props.get("profile_image")))
        return ProviderProfile(
            provider="KAKAO",
            oauth_id=str(me["id"]),
            email=email,
            email_verified=verified,
            name=_str(prof.get("nickname")) or _str(props.get("nickname")),
            picture=picture,
        )

    def authorize_url(self, *, state: str, code_challenge: str, nonce: str, login_hint: str | None) -> str:
        if not self.s.kakao_rest_api_key:
            raise ProviderAuthError("kakao_not_configured", 503, MSG_NOT_READY)
        q = {
            "client_id": self.s.kakao_rest_api_key,
            "redirect_uri": self.s.callback_uri("kakao"),
            "response_type": "code",
            "state": state,
        }
        if self.s.kakao_scope:
            q["scope"] = self.s.kakao_scope
        if self.s.kakao_use_pkce:
            q["code_challenge"] = code_challenge
            q["code_challenge_method"] = "S256"
        return f"{self.AUTHORIZE_URL}?{urlencode(q)}"

    async def exchange_code(self, code: str, *, code_verifier: str, nonce: str | None) -> ProviderProfile:
        if not self.s.kakao_rest_api_key:
            raise ProviderAuthError("kakao_not_configured", 503, MSG_NOT_READY)
        form = {
            "grant_type": "authorization_code",
            "client_id": self.s.kakao_rest_api_key,
            "redirect_uri": self.s.callback_uri("kakao"),
            "code": _check_token(code),
        }
        if self.s.kakao_client_secret:
            form["client_secret"] = self.s.kakao_client_secret
        if self.s.kakao_use_pkce:
            form["code_verifier"] = code_verifier
        try:
            r = await self.http.post(self.TOKEN_URL, data=form, timeout=8.0)
        except httpx.HTTPError:
            raise ProviderAuthError("kakao_unavailable", 502) from None
        if r.status_code != 200:
            log.warning("kakao token exchange failed status=%s", r.status_code)
            raise ProviderAuthError("kakao_code_rejected")
        access = (r.json() or {}).get("access_token")
        # 우리가 직접 받은 토큰이라 app_id 는 맞지만, 설정돼 있으면 한 번 더 본다.
        return await self.verify_access_token(access, require_app_id=False)

    async def unlink(self, oauth_id: str, *, user_access_token: str | None = None) -> str:
        """카카오 연결 끊기. 어드민 키가 있으면 그걸로, 없으면 앱이 준 사용자 토큰으로."""
        if self.s.kakao_admin_key:
            headers = {"Authorization": f"KakaoAK {self.s.kakao_admin_key}"}
            data = {"target_id_type": "user_id", "target_id": oauth_id}
        elif user_access_token:
            headers = {"Authorization": f"Bearer {user_access_token}"}
            data = None
        else:
            return "SKIPPED"
        try:
            r = await self.http.post(self.UNLINK_URL, headers=headers, data=data, timeout=8.0)
        except httpx.HTTPError:
            return "FAILED"
        if r.status_code != 200:
            log.warning("kakao unlink failed status=%s", r.status_code)
            return "FAILED"
        try:
            ok = str(r.json().get("id")) == str(oauth_id)
        except ValueError:
            ok = False
        return "OK" if ok else "FAILED"


class GoogleProvider:
    code = "GOOGLE"
    AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self, s: AuthSettings, http: httpx.AsyncClient):
        self.s, self.http = s, http

    @staticmethod
    def profile(claims: dict) -> ProviderProfile:
        email = _str(claims.get("email"))
        return ProviderProfile(
            provider="GOOGLE",
            oauth_id=claims["sub"],
            email=email,
            email_verified=bool(email) and claims.get("email_verified") in (True, "true"),
            name=_str(claims.get("name")),
            picture=_str(claims.get("picture")),
        )

    async def verify_id_token(self, id_token: str | None, *, nonce: str | None = None,
                              audiences: tuple[str, ...] | None = None) -> ProviderProfile:
        claims = await verify_google_id_token(
            _check_token(id_token),
            audiences=audiences if audiences is not None else self.s.google_client_ids,
            http=self.http,
            nonce=nonce,
        )
        return self.profile(claims)

    def authorize_url(self, *, state: str, code_challenge: str, nonce: str, login_hint: str | None) -> str:
        if not (self.s.google_web_client_id and self.s.google_client_secret):
            raise ProviderAuthError("google_not_configured", 503, MSG_NOT_READY)
        q = {
            "client_id": self.s.google_web_client_id,
            "redirect_uri": self.s.callback_uri("google"),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(q)}"

    async def exchange_code(self, code: str, *, code_verifier: str, nonce: str | None) -> ProviderProfile:
        if not (self.s.google_web_client_id and self.s.google_client_secret):
            raise ProviderAuthError("google_not_configured", 503, MSG_NOT_READY)
        form = {
            "grant_type": "authorization_code",
            "code": _check_token(code),
            "client_id": self.s.google_web_client_id,
            "client_secret": self.s.google_client_secret,
            "redirect_uri": self.s.callback_uri("google"),
            "code_verifier": code_verifier,
        }
        try:
            r = await self.http.post(self.TOKEN_URL, data=form, timeout=8.0)
        except httpx.HTTPError:
            raise ProviderAuthError("google_unavailable", 502) from None
        if r.status_code != 200:
            log.warning("google token exchange failed status=%s", r.status_code)
            raise ProviderAuthError("google_code_rejected")
        id_token = (r.json() or {}).get("id_token")
        if not id_token:
            raise ProviderAuthError("google_no_id_token", 502)
        # 서버 흐름의 ID 토큰은 웹 클라이언트 ID 로 나온다.
        return await self.verify_id_token(id_token, nonce=nonce, audiences=(self.s.google_web_client_id,))

    async def unlink(self, oauth_id: str, *, user_access_token: str | None = None) -> str:
        # 구글 토큰을 서버에 두지 않으므로 서버에서 끊을 수 없다. 앱이 GoogleSignIn.disconnect() 를 부른다.
        return "SKIPPED"


class FakeProvider:
    """AUTH_FAKE_PROVIDER=1 일 때만. 키 없이 앱↔서버 로그인 흐름을 끝까지 시험한다.

    모바일: accessToken = "fake:<id>[:<이름>]"
    서버 흐름: 인가 주소가 곧바로 우리 콜백으로 돌아오고, 코드에 PKCE challenge 를 담아 진짜처럼 확인한다.
    """

    code = "FAKE"

    def __init__(self, s: AuthSettings):
        self.s = s

    @staticmethod
    def parse(token: str | None) -> ProviderProfile:
        token = _check_token(token)
        parts = token.split(":", 2)
        if len(parts) < 2 or parts[0] != "fake" or not parts[1] or len(parts[1]) > 64:
            raise ProviderAuthError("fake_token_invalid")
        return ProviderProfile(provider="FAKE", oauth_id=parts[1], name=parts[2] if len(parts) > 2 else "시험 사용자")

    def verify_access_token(self, token: str | None) -> ProviderProfile:
        return self.parse(token)

    def authorize_url(self, *, state: str, code_challenge: str, nonce: str, login_hint: str | None) -> str:
        hint = (login_hint or "e2e-user").replace(":", "")[:64] or "e2e-user"
        code = f"{hint}.{code_challenge}"
        return f"{self.s.callback_uri('fake')}?{urlencode({'code': code, 'state': state})}"

    async def exchange_code(self, code: str, *, code_verifier: str, nonce: str | None) -> ProviderProfile:
        hint, _, challenge = _check_token(code).rpartition(".")
        if not hint or not pkce.verify(code_verifier, challenge):
            raise ProviderAuthError("fake_code_rejected")
        return ProviderProfile(provider="FAKE", oauth_id=hint, name="시험 사용자")

    async def unlink(self, oauth_id: str, *, user_access_token: str | None = None) -> str:
        return "OK"


class Providers:
    def __init__(self, s: AuthSettings, http: httpx.AsyncClient):
        self.s = s
        self.kakao = KakaoProvider(s, http)
        self.google = GoogleProvider(s, http)
        self.fake = FakeProvider(s) if s.fake_provider else None

    def get(self, name: str) -> KakaoProvider | GoogleProvider | FakeProvider:
        p = {"kakao": self.kakao, "google": self.google, "fake": self.fake}.get(name.lower())
        if p is None:
            raise AuthError(404, "unknown_provider", MSG_NOT_READY)
        return p
