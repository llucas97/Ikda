"""로그인 뒤 앱으로 돌아가는 주소 (AsOne oauth/OAuthClientRedirect 와 같은 역할).

AsOne 은 딥링크 쿼리에 accessToken/refreshToken 을 그대로 실었다. 주소는 브라우저 기록·로그·
다른 앱(같은 스킴을 가로챈 앱)에 새기 쉬워서, 여기서는 1회용 로그인 코드만 싣고 앱이
POST /api/auth/token 에 PKCE code_verifier 와 함께 보내 토큰으로 바꾼다 (RFC 8252).
실패도 같은 딥링크로 돌려보내 앱 로그인 화면이 한 줄로 안내한다(브라우저에 오류 JSON 을 띄우지 않는다).
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from .config import DEFAULT_APP_CALLBACK, AuthSettings


def is_allowed(s: AuthSettings, uri: str | None) -> bool:
    # 정확히 같은 문자열만. 앞부분 일치·와일드카드는 열린 리다이렉트가 된다.
    return bool(uri) and uri in s.app_redirect_uris


def default_callback(s: AuthSettings) -> str:
    return s.app_redirect_uris[0] if s.app_redirect_uris else DEFAULT_APP_CALLBACK


def _join(base: str, params: dict[str, str | None]) -> str:
    q = urlencode({k: v for k, v in params.items() if v is not None}, quote_via=quote)
    return base + ("&" if "?" in base else "?") + q


def success_url(base: str, login_code: str, app_state: str | None) -> str:
    return _join(base, {"code": login_code, "state": app_state})


def login_failed_url(base: str, *, provider: str, reason: str, message: str, app_state: str | None) -> str:
    return _join(base, {"error": "login_failed", "provider": provider, "reason": reason,
                        "message": message, "state": app_state})
