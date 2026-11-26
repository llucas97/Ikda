"""FastAPI 의존성: 설정, 제공자 HTTP, 요청 정보, 현재 회원 (AsOne JwtAuthenticationFilter 역할)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session, session_scope
from .config import AuthSettings, get_settings
from .errors import MSG_LOGIN_AGAIN, AuthError
from .models import User
from .providers import Providers
from .service import ClientMeta, authenticate
from .tokens import AccessClaims


def settings_dep() -> AuthSettings:
    return get_settings()


async def get_http() -> AsyncIterator[httpx.AsyncClient]:
    """제공자 호출용. 테스트는 app.dependency_overrides 로 MockTransport 클라이언트를 넣는다."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False) as client:
        yield client


def providers_dep(s: AuthSettings = Depends(settings_dep), http: httpx.AsyncClient = Depends(get_http)) -> Providers:
    return Providers(s, http)


def client_ip(request: Request) -> str | None:
    # 프록시(Cloud Run 등) 뒤에서만 X-Forwarded-For 를 믿는다. 아니면 누구나 IP 를 꾸밀 수 있다.
    if os.getenv("TRUST_PROXY_HEADERS") == "1":
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:50]
    return request.client.host[:50] if request.client else None


def client_meta(request: Request, device_id: str | None = None, device_os: str | None = None) -> ClientMeta:
    os_cd = (device_os or "").upper()[:30] or None
    return ClientMeta(
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        device_id=(device_id or "")[:100] or None,
        device_os=os_cd,
        client_type="WEB" if os_cd == "WEB" else "APP",
    )


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


@dataclass(frozen=True)
class AuthContext:
    user: User
    claims: AccessClaims


async def current_auth(request: Request, db: AsyncSession = Depends(get_session),
                       s: AuthSettings = Depends(settings_dep)) -> AuthContext:
    token = bearer_token(request)
    if token is None:
        raise AuthError(401, "login_required", MSG_LOGIN_AGAIN)
    user, claims = await authenticate(db, s, token)
    return AuthContext(user, claims)


async def optional_auth(request: Request, s: AuthSettings = Depends(settings_dep)) -> AuthContext | None:
    """토큰이 없으면 None(DB 도 열지 않는다). 있는데 틀리면 401 (조용히 손님으로 넘기지 않는다)."""
    token = bearer_token(request)
    if token is None:
        return None
    async with session_scope() as db:
        user, claims = await authenticate(db, s, token)
    return AuthContext(user, claims)
