"""우리 토큰. access 는 짧은 JWT(HS256), refresh 는 원문을 저장하지 않는 무작위 문자열.

AsOne JwtUtil 과 같은 점: tokenType 클레임으로 access/refresh 를 가른다(여기서는 typ=access).
다른 점: refresh 를 JWT 로 만들지 않는다. 서버에 SHA-256 만 두고, 한 번 쓰면 바꾼다(회전).
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

from .config import AuthSettings
from .errors import MSG_LOGIN_AGAIN, AuthError

ALGORITHM = "HS256"
ACCESS_TYP = "access"


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 256비트


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class AccessClaims:
    user_no: int
    sid: str
    jti: str
    user_type: str
    exp: int


def issue_access_token(s: AuthSettings, *, user_no: int, user_type: str, sid: str, jti: str,
                       now: datetime) -> tuple[str, datetime]:
    exp = now + timedelta(seconds=s.access_ttl_s)
    claims = {
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "sub": str(user_no),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "sid": sid,
        "typ": ACCESS_TYP,
        "utype": user_type,
    }
    return jwt.encode(claims, s.jwt_secret, algorithm=ALGORITHM, headers={"typ": "at+jwt"}), exp


def decode_access_token(s: AuthSettings, token: str) -> AccessClaims:
    try:
        claims = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[ALGORITHM],
            audience=s.jwt_audience,
            issuer=s.jwt_issuer,
            leeway=10,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError(401, "token_expired", MSG_LOGIN_AGAIN) from None
    except jwt.PyJWTError:
        raise AuthError(401, "invalid_token", MSG_LOGIN_AGAIN) from None
    if claims.get("typ") != ACCESS_TYP or not claims.get("sid"):
        raise AuthError(401, "invalid_token", MSG_LOGIN_AGAIN)
    try:
        user_no = int(claims["sub"])
    except (TypeError, ValueError):
        raise AuthError(401, "invalid_token", MSG_LOGIN_AGAIN) from None
    return AccessClaims(user_no=user_no, sid=claims["sid"], jti=claims["jti"],
                        user_type=claims.get("utype", ""), exp=int(claims["exp"]))
