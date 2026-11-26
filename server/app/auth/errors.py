"""로그인 오류. 응답 모양은 /api/analyze 와 같다: {"error": {"code", "userMessage"}}"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

MSG_LOGIN_AGAIN = "다시 로그인해 주세요."
MSG_LOGIN_FAILED = "로그인하지 못했어요. 다시 해 주세요."
MSG_NOT_READY = "지금은 이 방법으로 로그인할 수 없어요."


class AuthError(Exception):
    def __init__(self, status: int, code: str, user_message: str = MSG_LOGIN_FAILED):
        super().__init__(code)
        self.status = status
        self.code = code
        self.user_message = user_message


class ProviderAuthError(AuthError):
    """소셜 제공자가 토큰을 거절했거나 응답이 이상하다. 사유 코드는 로그에만 남긴다."""

    def __init__(self, code: str, status: int = 401, user_message: str = MSG_LOGIN_FAILED):
        super().__init__(status, code, user_message)


async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'} if exc.status == 401 else None
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "userMessage": exc.user_message}},
        headers=headers,
    )
