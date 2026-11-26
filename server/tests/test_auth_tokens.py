"""우리 JWT, PKCE, 돌아갈 주소, JWKS 캐시, 구글 ID 토큰 검증 (단위)."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app.auth import pkce, redirect
from app.auth.config import AuthSettings
from app.auth.errors import AuthError, ProviderAuthError
from app.auth.oidc import JwksCache, verify_google_id_token
from app.auth.tokens import decode_access_token, issue_access_token

from conftest import GOOGLE_ANDROID, GOOGLE_WEB, ProviderHTTP, RsaKey, _OTHER, google_claims

S = AuthSettings(jwt_secret="unit-secret-0123456789-abcdefghijklmnop")
NOW = datetime.now(timezone.utc)


def _issue(s=S, now=NOW, **kw):
    args = {"user_no": 7, "user_type": "SENIOR", "sid": "fam1", "jti": "j1", "now": now, **kw}
    return issue_access_token(s, **args)[0]


def test_access_token_roundtrip_and_claims():
    tok = _issue()
    c = decode_access_token(S, tok)
    assert (c.user_no, c.sid, c.jti, c.user_type) == (7, "fam1", "j1", "SENIOR")
    raw = jwt.decode(tok, options={"verify_signature": False})
    assert raw["iss"] == "ilgeodeurim" and raw["aud"] == "ilgeodeurim-app" and raw["typ"] == "access"
    assert raw["exp"] - raw["iat"] == 15 * 60
    assert jwt.get_unverified_header(tok)["alg"] == "HS256"


@pytest.mark.parametrize("mutate,code", [
    (lambda: _issue(now=NOW - timedelta(hours=1)), "token_expired"),
    (lambda: _issue(s=AuthSettings(jwt_secret="another-secret-0123456789-abcdefghijk")), "invalid_token"),
    (lambda: _issue(s=AuthSettings(jwt_secret=S.jwt_secret, jwt_audience="other")), "invalid_token"),
    (lambda: _issue(s=AuthSettings(jwt_secret=S.jwt_secret, jwt_issuer="evil")), "invalid_token"),
    (lambda: jwt.encode({"sub": "7", "sid": "f", "typ": "access", "jti": "j", "iss": "ilgeodeurim",
                         "aud": "ilgeodeurim-app", "iat": int(time.time()), "exp": int(time.time()) + 60},
                        None, algorithm="none"), "invalid_token"),
    (lambda: jwt.encode({"sub": "7", "sid": "f", "typ": "refresh", "jti": "j", "iss": "ilgeodeurim",
                         "aud": "ilgeodeurim-app", "iat": int(time.time()), "exp": int(time.time()) + 60},
                        S.jwt_secret, algorithm="HS256"), "invalid_token"),
    (lambda: "not.a.jwt", "invalid_token"),
])
def test_access_token_rejections(mutate, code):
    with pytest.raises(AuthError) as e:
        decode_access_token(S, mutate())
    assert e.value.code == code and e.value.status == 401


def test_pkce_rfc7636_vector():
    v = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce.s256(v) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert pkce.verify(v, "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
    assert not pkce.verify("short", pkce.s256("short"))  # 43자 미만 verifier 는 거절
    assert pkce.valid_challenge(pkce.s256(pkce.new_verifier()))
    assert not pkce.valid_challenge("plain-challenge")


def test_redirect_urls():
    s = AuthSettings(jwt_secret="x" * 32, app_redirect_uris=("ilgeodeurim://oauth/callback",))
    assert redirect.is_allowed(s, "ilgeodeurim://oauth/callback")
    assert not redirect.is_allowed(s, "ilgeodeurim://oauth/callback/../evil")
    assert not redirect.is_allowed(s, "https://evil.example/cb")
    url = redirect.login_failed_url("ilgeodeurim://oauth/callback", provider="kakao", reason="cancelled",
                                    message="로그인을 취소했어요.", app_state="a b")
    assert "error=login_failed" in url and "state=a%20b" in url and "+" not in url
    assert redirect.success_url("x://cb?keep=1", "c0de", None) == "x://cb?keep=1&code=c0de"


# ---------- JWKS / 구글 ID 토큰 ----------

def _verify(http: ProviderHTTP, token: str, jwks: JwksCache, **kw):
    async def go():
        async with http.client() as c:
            return await verify_google_id_token(token, audiences=(GOOGLE_WEB, GOOGLE_ANDROID), http=c,
                                                jwks=jwks, **kw)
    return asyncio.run(go())


def _hs256_with_public_key(k: RsaKey) -> str:
    def b64(b: bytes) -> bytes:
        return base64.urlsafe_b64encode(b).rstrip(b"=")
    signing = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": k.kid}).encode()) + b"." + \
        b64(json.dumps(google_claims()).encode())
    return (signing + b"." + b64(hmac.new(k.public_pem, signing, hashlib.sha256).digest())).decode()


@pytest.fixture
def jwks():
    return JwksCache("https://www.googleapis.com/oauth2/v3/certs")


def test_google_id_token_ok_and_cached(jwks):
    http = ProviderHTTP()
    claims = _verify(http, http.key.sign(google_claims()), jwks)
    assert claims["sub"] == "g-sub-1"
    _verify(http, http.key.sign(google_claims(aud=GOOGLE_ANDROID)), jwks)  # 안드로이드 클라이언트 aud 도 된다
    assert http.jwks_hits == 1  # Cache-Control max-age 동안 다시 받지 않는다


@pytest.mark.parametrize("token_fn,code", [
    (lambda k: k.sign(google_claims(aud="someone-else.apps.googleusercontent.com")), "id_token_bad_aud"),
    (lambda k: k.sign(google_claims(iss="https://evil.example")), "id_token_bad_iss"),
    (lambda k: k.sign(google_claims(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200)), "id_token_expired"),
    (lambda k: k.sign(google_claims(iat=int(time.time()) + 3600, exp=int(time.time()) + 7200)), "id_token_invalid"),
    (lambda k: _OTHER.sign(google_claims()), "id_token_invalid"),  # 같은 kid, 다른 키로 서명
    (lambda k: k.sign({**google_claims(), "aud": [GOOGLE_WEB, "x"], "azp": "x"}), "id_token_bad_azp"),
    (lambda k: k.sign({k2: v for k2, v in google_claims().items() if k2 != "sub"}), "id_token_invalid"),
    # 알고리즘 바꿔치기: 공개키를 HMAC 비밀로 써서 HS256 서명
    (lambda k: _hs256_with_public_key(k), "id_token_bad_alg"),
    (lambda k: "garbage", "id_token_malformed"),
])
def test_google_id_token_rejections(jwks, token_fn, code):
    http = ProviderHTTP()
    with pytest.raises(ProviderAuthError) as e:
        _verify(http, token_fn(http.key), jwks)
    assert e.value.code == code


def test_google_nonce_checked(jwks):
    http = ProviderHTTP()
    tok = http.key.sign(google_claims(nonce="n-1"))
    assert _verify(http, tok, jwks, nonce="n-1")["nonce"] == "n-1"
    with pytest.raises(ProviderAuthError) as e:
        _verify(http, tok, jwks, nonce="n-2")
    assert e.value.code == "id_token_bad_nonce"


def test_jwks_unknown_kid_refetch_is_rate_limited():
    t = [1000.0]
    jwks = JwksCache("https://www.googleapis.com/oauth2/v3/certs", min_refetch_s=60, clock=lambda: t[0])
    http = ProviderHTTP()
    _verify(http, http.key.sign(google_claims()), jwks)
    rotated = RsaKey("google-kid-2")
    with pytest.raises(ProviderAuthError):  # 방금 받았으니 다시 받지 않는다
        _verify(http, rotated.sign(google_claims()), jwks)
    assert http.jwks_hits == 1
    t[0] += 61
    for _ in range(3):  # 모르는 kid 를 마구 보내도
        with pytest.raises(ProviderAuthError):
            _verify(http, rotated.sign(google_claims()), jwks)
    assert http.jwks_hits == 2  # 첫 조회 + 한 번만 다시 받음
    t[0] += 61
    http.key = rotated  # 구글이 키를 바꿨다
    assert _verify(http, rotated.sign(google_claims()), jwks)["sub"] == "g-sub-1"
    assert http.jwks_hits == 3


def test_jwks_outage_uses_stale_keys_then_503():
    t = [0.0]
    jwks = JwksCache("https://www.googleapis.com/oauth2/v3/certs", clock=lambda: t[0])
    http = ProviderHTTP()
    tok = http.key.sign(google_claims())
    _verify(http, tok, jwks)
    t[0] += 10 ** 6  # 캐시 만료
    http.jwks_status = 500
    assert _verify(http, tok, jwks)["sub"] == "g-sub-1"  # 예전 키로 버틴다
    with pytest.raises(ProviderAuthError) as e:
        _verify(http, RsaKey("new-kid").sign(google_claims()), JwksCache("https://www.googleapis.com/oauth2/v3/certs"))
    assert e.value.code == "jwks_unavailable" and e.value.status == 503


def test_google_not_configured():
    http = ProviderHTTP()

    async def go():
        async with http.client() as c:
            await verify_google_id_token(http.key.sign(google_claims()), audiences=(), http=c)
    with pytest.raises(ProviderAuthError) as e:
        asyncio.run(go())
    assert e.value.status == 503


def test_httpx_mock_transport_is_used():
    # 실수로 진짜 구글에 나가지 않는지: 모르는 주소는 404 를 돌려준다
    http = ProviderHTTP()

    async def go():
        async with http.client() as c:
            return (await c.get("https://example.com/x")).status_code
    assert asyncio.run(go()) == 404 and isinstance(http.calls[0], httpx.Request)
