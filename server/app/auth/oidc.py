"""OIDC ID 토큰 검증 (구글). 공개키는 JWKS 에서 받아 Cache-Control 동안 둔다."""
from __future__ import annotations

import hmac
import json
import logging
import re
import time
from typing import Any, Callable, Iterable

import httpx
import jwt

from .errors import MSG_NOT_READY, ProviderAuthError

log = logging.getLogger("ilgeodeurim.auth")

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
ALLOWED_ALGS = ("RS256",)
LEEWAY_S = 60
MAX_TOKEN_LEN = 8192

_MAX_AGE = re.compile(r"max-age=(\d+)")


class JwksCache:
    """kid → 공개키. 모르는 kid 가 오면 다시 받되, 남이 마구 보내도 min_refetch_s 에 한 번만."""

    def __init__(self, url: str, *, default_ttl_s: int = 3600, min_refetch_s: int = 60,
                 clock: Callable[[], float] = time.monotonic):
        self.url = url
        self.default_ttl_s = default_ttl_s
        self.min_refetch_s = min_refetch_s
        self.clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._expires_at = 0.0
        self._fetched_at: float | None = None

    def clear(self) -> None:
        self._keys, self._expires_at, self._fetched_at = {}, 0.0, None

    async def _fetch(self, http: httpx.AsyncClient) -> None:
        self._fetched_at = self.clock()
        r = await http.get(self.url, timeout=5.0)
        r.raise_for_status()
        keys: dict[str, jwt.PyJWK] = {}
        for jwk in r.json().get("keys", []):
            if jwk.get("kty") != "RSA" or not jwk.get("kid") or jwk.get("use", "sig") != "sig":
                continue
            try:
                keys[jwk["kid"]] = jwt.PyJWK(jwk, algorithm=jwk.get("alg", "RS256"))
            except jwt.PyJWKError:
                continue
        if not keys:
            raise ValueError("JWKS 에 쓸 수 있는 키가 없다")
        m = _MAX_AGE.search(r.headers.get("cache-control", ""))
        ttl = int(m.group(1)) if m else self.default_ttl_s
        self._keys = keys
        self._expires_at = self.clock() + min(max(ttl, 60), 24 * 3600)

    async def get_key(self, kid: str, http: httpx.AsyncClient) -> jwt.PyJWK:
        now = self.clock()
        fresh = now < self._expires_at
        if fresh and kid in self._keys:
            return self._keys[kid]
        may_fetch = not fresh or self._fetched_at is None or now - self._fetched_at >= self.min_refetch_s
        if may_fetch:
            try:
                await self._fetch(http)
            except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
                log.warning("jwks fetch failed url=%s err=%s", self.url, type(e).__name__)
                if kid in self._keys:  # 받기에 실패하면 예전 키라도 쓴다
                    return self._keys[kid]
                raise ProviderAuthError("jwks_unavailable", 503, MSG_NOT_READY) from None
        key = self._keys.get(kid)
        if key is None:
            raise ProviderAuthError("id_token_unknown_kid")
        return key


GOOGLE_JWKS = JwksCache(GOOGLE_JWKS_URL)


async def verify_google_id_token(token: str, *, audiences: Iterable[str], http: httpx.AsyncClient,
                                 nonce: str | None = None, jwks: JwksCache | None = None) -> dict[str, Any]:
    """서명(RS256, JWKS), iss, aud(우리 클라이언트 ID 중 하나), exp/iat, sub, (있으면) nonce 를 본다."""
    auds = [a for a in audiences if a]
    if not auds:
        raise ProviderAuthError("google_not_configured", 503, MSG_NOT_READY)
    if not token or len(token) > MAX_TOKEN_LEN:
        raise ProviderAuthError("id_token_malformed")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise ProviderAuthError("id_token_malformed") from None
    if header.get("alg") not in ALLOWED_ALGS:
        raise ProviderAuthError("id_token_bad_alg")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise ProviderAuthError("id_token_malformed")

    key = await (jwks or GOOGLE_JWKS).get_key(kid, http)
    try:
        claims = jwt.decode(
            token,
            key.key,
            algorithms=list(ALLOWED_ALGS),
            audience=auds,
            leeway=LEEWAY_S,
            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError:
        raise ProviderAuthError("id_token_expired") from None
    except jwt.InvalidAudienceError:
        raise ProviderAuthError("id_token_bad_aud") from None
    except jwt.PyJWTError:
        raise ProviderAuthError("id_token_invalid") from None

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ProviderAuthError("id_token_bad_iss")
    aud = claims.get("aud")
    # aud 가 여러 개면 azp 가 우리 클라이언트여야 한다 (OIDC Core 3.1.3.7).
    if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") not in auds:
        raise ProviderAuthError("id_token_bad_azp")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise ProviderAuthError("id_token_invalid")
    if nonce is not None and not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ProviderAuthError("id_token_bad_nonce")
    return claims
