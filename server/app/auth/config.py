"""로그인 설정. 모두 환경변수로 바꾼다 (키는 코드·저장소에 두지 않는다)."""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache

log = logging.getLogger("ilgeodeurim.auth")

DEFAULT_APP_CALLBACK = "ilgeodeurim://oauth/callback"


def _list(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(v.strip() for v in os.getenv(name, default).split(",") if v.strip())


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str
    jwt_issuer: str = "ilgeodeurim"
    jwt_audience: str = "ilgeodeurim-app"
    access_ttl_s: int = 15 * 60
    refresh_ttl_s: int = 60 * 24 * 3600
    session_max_s: int = 365 * 24 * 3600
    refresh_reuse_grace_s: int = 30
    max_sessions_per_user: int = 5
    authorize_ttl_s: int = 600
    login_code_ttl_s: int = 120

    public_base_url: str = "http://localhost:8000"
    app_redirect_uris: tuple[str, ...] = (DEFAULT_APP_CALLBACK,)

    kakao_rest_api_key: str = ""
    kakao_client_secret: str = ""
    kakao_app_id: str = ""
    kakao_admin_key: str = ""
    kakao_redirect_uri: str = ""
    kakao_use_pkce: bool = True
    kakao_scope: str = ""

    google_client_ids: tuple[str, ...] = field(default_factory=tuple)
    google_web_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    fake_provider: bool = False

    def callback_uri(self, provider: str) -> str:
        override = {"kakao": self.kakao_redirect_uri, "google": self.google_redirect_uri}.get(provider, "")
        return override or f"{self.public_base_url.rstrip('/')}/api/auth/{provider}/callback"


@lru_cache(maxsize=1)
def get_settings() -> AuthSettings:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        # 개발용. 서버를 다시 켜면 모든 토큰이 무효가 된다. 운영에서는 반드시 넣는다.
        secret = secrets.token_urlsafe(48)
        log.warning("JWT_SECRET 이 없어 임시 키를 만들었어요. 운영에서는 32바이트 이상 키를 넣으세요.")
    elif len(secret.encode()) < 32:
        raise RuntimeError("JWT_SECRET 은 32바이트 이상이어야 해요 (HS256).")

    web_id = os.getenv("GOOGLE_WEB_CLIENT_ID", "").strip()
    ids = _list("GOOGLE_CLIENT_IDS") or _list("GOOGLE_CLIENT_ID")
    if web_id and web_id not in ids:
        ids = (web_id, *ids)

    return AuthSettings(
        jwt_secret=secret,
        jwt_issuer=os.getenv("JWT_ISSUER", "ilgeodeurim"),
        jwt_audience=os.getenv("JWT_AUDIENCE", "ilgeodeurim-app"),
        access_ttl_s=_int("ACCESS_TOKEN_TTL_MIN", 15) * 60,
        refresh_ttl_s=_int("REFRESH_TOKEN_TTL_DAYS", 60) * 24 * 3600,
        session_max_s=_int("SESSION_MAX_DAYS", 365) * 24 * 3600,
        refresh_reuse_grace_s=_int("REFRESH_REUSE_GRACE_S", 30),
        max_sessions_per_user=_int("MAX_SESSIONS_PER_USER", 5),
        authorize_ttl_s=_int("OAUTH_STATE_TTL_S", 600),
        login_code_ttl_s=_int("LOGIN_CODE_TTL_S", 120),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"),
        app_redirect_uris=_list("APP_REDIRECT_URIS", DEFAULT_APP_CALLBACK),
        kakao_rest_api_key=os.getenv("KAKAO_REST_API_KEY", ""),
        kakao_client_secret=os.getenv("KAKAO_CLIENT_SECRET", ""),
        kakao_app_id=os.getenv("KAKAO_APP_ID", ""),
        kakao_admin_key=os.getenv("KAKAO_ADMIN_KEY", ""),
        kakao_redirect_uri=os.getenv("KAKAO_REDIRECT_URI", ""),
        kakao_use_pkce=os.getenv("KAKAO_USE_PKCE", "1") != "0",
        kakao_scope=os.getenv("KAKAO_SCOPE", ""),
        google_client_ids=ids,
        google_web_client_id=web_id or (ids[0] if ids else ""),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", ""),
        fake_provider=os.getenv("AUTH_FAKE_PROVIDER") == "1",
    )


def reset_settings() -> None:
    get_settings.cache_clear()
