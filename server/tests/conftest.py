"""로그인 테스트 공용: 임시 SQLite, 가짜 카카오·구글 HTTP(MockTransport), 시험용 RSA 키."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import db as dbmod
from app import push as pushmod
from app.auth import config, oidc, pkce
from app.auth.deps import AuthContext, current_auth, get_http
from app.auth.routes import install
from app.family import routes as family_routes
from app.push import FakePushSender, push_sender_dep

GOOGLE_WEB = "web-client.apps.googleusercontent.com"
GOOGLE_ANDROID = "android-client.apps.googleusercontent.com"
KAKAO_APP_ID = "1234"
APP_CB = "ilgeodeurim://oauth/callback"


def _b64(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class RsaKey:
    def __init__(self, kid: str):
        self.kid = kid
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub = self.private.public_key().public_numbers()
        self.jwk = {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": _b64(pub.n), "e": _b64(pub.e)}
        self.public_pem = self.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    def sign(self, claims: dict, **header) -> str:
        return jwt.encode(claims, self.private, algorithm="RS256", headers={"kid": self.kid, **header})


_KEY = RsaKey("google-kid-1")
_OTHER = RsaKey("google-kid-1")  # 같은 kid, 다른 키 (서명 위조)


def google_claims(sub: str = "g-sub-1", **over) -> dict:
    now = int(time.time())
    c = {"iss": "https://accounts.google.com", "aud": GOOGLE_WEB, "azp": GOOGLE_ANDROID, "sub": sub,
         "email": "grandma@example.com", "email_verified": True, "name": "김순자",
         "picture": "https://lh3.googleusercontent.com/a/x", "iat": now, "exp": now + 3600}
    c.update(over)
    return c


def kakao_me(uid: int, nickname: str = "박영감", email: str | None = None) -> dict:
    account = {"profile": {"nickname": nickname, "profile_image_url": "https://k.kakaocdn.net/p.jpg",
                           "is_default_image": False}}
    if email:
        account.update({"has_email": True, "email_needs_agreement": False, "is_email_valid": True,
                        "is_email_verified": True, "email": email})
    else:
        account.update({"has_email": False})
    return {"id": uid, "connected_at": "2026-11-17T00:00:00Z", "kakao_account": account}


class ProviderHTTP:
    """카카오·구글 서버 흉내. 요청을 모두 calls 에 남긴다."""

    def __init__(self):
        self.key = _KEY
        self.calls: list[httpx.Request] = []
        self.kakao_tokens: dict[str, dict] = {"kakao-good": {"id": 1001, "app_id": int(KAKAO_APP_ID),
                                                             "me": kakao_me(1001)}}
        self.kakao_status: int | None = None  # 강제로 낼 상태코드
        self.unlink_status = 200
        self.jwks_hits = 0
        self.jwks_status = 200
        self.google_code: dict | None = None  # {"code","challenge","nonce","sub"}
        self.kakao_code: dict | None = None  # {"code","challenge","token"}

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def handle(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        host, path = req.url.host, req.url.path
        auth = req.headers.get("authorization", "")
        bearer = auth[7:] if auth.startswith("Bearer ") else None
        form = parse_qs(req.content.decode()) if req.method == "POST" and req.content else {}
        f = {k: v[0] for k, v in form.items()}

        if host == "kapi.kakao.com":
            if self.kakao_status:
                return httpx.Response(self.kakao_status, json={"msg": "boom", "code": -1})
            if path == "/v1/user/unlink":
                if self.unlink_status != 200:
                    return httpx.Response(self.unlink_status, json={"msg": "fail", "code": -1})
                if auth.startswith("KakaoAK "):
                    return httpx.Response(200, json={"id": int(f["target_id"])})
                t = self.kakao_tokens.get(bearer or "")
                return httpx.Response(200, json={"id": t["id"]}) if t else httpx.Response(401, json={"code": -401})
            t = self.kakao_tokens.get(bearer or "")
            if t is None:
                return httpx.Response(401, json={"msg": "this access token does not exist", "code": -401})
            if path == "/v1/user/access_token_info":
                return httpx.Response(200, json={"id": t["id"], "expires_in": 7199, "app_id": t["app_id"]})
            if path == "/v2/user/me":
                return httpx.Response(200, json=t["me"])
        if host == "kauth.kakao.com" and path == "/oauth/token":
            c = self.kakao_code
            if not c or f.get("code") != c["code"] or pkce.s256(f.get("code_verifier", "")) != c["challenge"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": c["token"], "token_type": "bearer"})
        if host == "www.googleapis.com" and path == "/oauth2/v3/certs":
            self.jwks_hits += 1
            if self.jwks_status != 200:
                return httpx.Response(self.jwks_status)
            return httpx.Response(200, json={"keys": [self.key.jwk]},
                                  headers={"Cache-Control": "public, max-age=19000, must-revalidate"})
        if host == "oauth2.googleapis.com" and path == "/token":
            c = self.google_code
            if not c or f.get("code") != c["code"] or pkce.s256(f.get("code_verifier", "")) != c["challenge"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            idt = self.key.sign(google_claims(c.get("sub", "g-web-1"), aud=GOOGLE_WEB, azp=GOOGLE_WEB,
                                              nonce=c["nonce"]))
            return httpx.Response(200, json={"access_token": "ya29.x", "id_token": idt, "expires_in": 3599})
        return httpx.Response(404, json={"error": f"unmocked {host}{path}"})

    def hits(self, path: str) -> list[httpx.Request]:
        return [r for r in self.calls if r.url.path == path]


# 시험은 절대 실제 AI 를 부르지 않는다. 개발 PC 에 GEMINI_API_KEY 가 있어도 fake.
os.environ["AI_PROVIDER"] = "fake"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

ENV = {
    "JWT_SECRET": "test-secret-0123456789-abcdefghijklmnop",
    "AI_PROVIDER": "fake",
    "KAKAO_APP_ID": KAKAO_APP_ID,
    "KAKAO_REST_API_KEY": "kakao-rest-key",
    "KAKAO_CLIENT_SECRET": "kakao-secret",
    "GOOGLE_CLIENT_IDS": f"{GOOGLE_WEB},{GOOGLE_ANDROID}",
    "GOOGLE_WEB_CLIENT_ID": GOOGLE_WEB,
    "GOOGLE_CLIENT_SECRET": "google-secret",
    "PUBLIC_BASE_URL": "http://testserver",
    "APP_REDIRECT_URIS": f"{APP_CB},http://localhost:5000/auth/callback",
    "AUTH_FAKE_PROVIDER": "1",
}
CLEAR = ("KAKAO_ADMIN_KEY", "REFRESH_REUSE_GRACE_S", "REFRESH_TOKEN_TTL_DAYS", "SESSION_MAX_DAYS",
         "MAX_SESSIONS_PER_USER", "LOGIN_CODE_TTL_S", "OAUTH_STATE_TTL_S", "ACCESS_TOKEN_TTL_MIN",
         "GOOGLE_CLIENT_ID", "KAKAO_USE_PKCE", "TRUST_PROXY_HEADERS", "DB_AUTO_CREATE", "DB_NULL_POOL",
         "AUTH_REQUIRED_FOR_ANALYZE", "PUSH_PROVIDER", "FCM_SERVICE_ACCOUNT_FILE", "FCM_SERVICE_ACCOUNT_JSON",
         "FCM_PROJECT_ID", "GOOGLE_APPLICATION_CREDENTIALS", "QUALITY_CHECK", "QUALITY_BLUR_MIN", "DEBUG_USAGE",
         "FAMILY_INVITE_TTL_MIN", "FAMILY_FAIL_LIMIT", "FAMILY_FAIL_LIMIT_IP", "FAMILY_SEND_DAILY_LIMIT",
         "FAMILY_MAX_CHILDREN", "FAMILY_MAX_SENIORS", "AI_PROVIDER", "GEMINI_API_KEY", "ANTHROPIC_API_KEY")


def make_test_app(http: ProviderHTTP) -> FastAPI:
    app = FastAPI()
    install(app)
    family_routes.install(app)
    fake_push = FakePushSender()
    app.state.fake_push = fake_push
    app.dependency_overrides[push_sender_dep] = lambda: fake_push

    @app.get("/probe/me")
    async def probe(auth: AuthContext = Depends(current_auth)):
        return {"userNo": auth.user.user_no, "sid": auth.claims.sid}

    async def _http():
        async with http.client() as c:
            yield c

    app.dependency_overrides[get_http] = _http
    return app


class Env:
    def __init__(self, monkeypatch):
        self.mp = monkeypatch

    def set(self, **kv):
        for k, v in kv.items():
            self.mp.setenv(k, str(v))
        config.reset_settings()


TABLES = ("ct_family_log", "ct_push_log", "ct_document_share", "ct_document_todo", "ct_document",
          "ct_family_invite", "ct_family_link", "ct_user_family",
          "ct_oauth_authorize", "ct_user_login_log", "ct_user_push_token", "ct_user_access", "ct_user_oauth", "ct_user")


async def _truncate_pg() -> None:
    from sqlalchemy import text
    async with dbmod.session_scope() as s:
        await s.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        await s.commit()
    await dbmod.reset()  # 연결 풀이 이 이벤트 루프에 묶이지 않게


@pytest.fixture
def env(tmp_path, monkeypatch):
    """TEST_DATABASE_URL=postgresql://... 이면 그 DB(db/migrate.py 로 표를 만든 것)로 돌린다."""
    for k in CLEAR:
        monkeypatch.delenv(k, raising=False)
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    pg = os.getenv("TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", pg or f"sqlite+aiosqlite:///{(tmp_path / 'auth.db').as_posix()}")
    if pg:
        monkeypatch.setenv("DB_NULL_POOL", "1")
    config.reset_settings()
    pushmod.reset_sender()
    asyncio.run(dbmod.reset())
    if pg:
        asyncio.run(_truncate_pg())
    oidc.GOOGLE_JWKS.clear()
    yield Env(monkeypatch)
    asyncio.run(dbmod.reset())
    config.reset_settings()
    pushmod.reset_sender()
    oidc.GOOGLE_JWKS.clear()


@pytest.fixture
def http(env) -> ProviderHTTP:
    return ProviderHTTP()


@pytest.fixture
def client(env, http):
    with TestClient(make_test_app(http), follow_redirects=False) as c:
        yield c


def run_db(fn):
    """테스트에서 DB 를 직접 들여다볼 때: run_db(lambda s: s.scalars(...))"""
    async def go():
        async with dbmod.session_scope() as s:
            return await fn(s)
    return asyncio.run(go())


def login_fake(client, uid="u1", **extra) -> dict:
    r = client.post("/api/auth/fake", json={"accessToken": f"fake:{uid}", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


def query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False)


# ---------- Phase 3: 가족·서류·푸시·품질 ----------

# 디코딩할 수 없는 PNG (품질 검사를 건너뛴다) — 기존 테스트와 같은 것
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def pushes(client) -> FakePushSender:
    return client.app.state.fake_push


def add_push_token(client, tokens: dict, token: str, platform: str = "ANDROID") -> None:
    r = client.post("/api/me/push-token", headers=bearer(tokens), json={"pushToken": token, "platform": platform})
    assert r.status_code == 204, r.text


def doc_image(*, w: int = 900, h: int = 1200, blur: float = 0, brightness: float = 1.0, fmt: str = "JPEG",
              color=None, comment: bytes | None = None) -> bytes:
    """글씨 줄이 있는 가짜 서류 사진."""
    import io

    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

    if color is not None:
        img = Image.new("RGB", (w, h), color)
    else:
        img = Image.new("RGB", (w, h), (246, 244, 238))
        d = ImageDraw.Draw(img)
        font = ImageFont.load_default(size=26)
        for i, y in enumerate(range(90, h - 90, 44)):
            d.text((70, y), f"Electric bill line {i}: 32,400 KRW due 2026-11-25", fill=(25, 25, 25), font=font)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    b = io.BytesIO()
    kw = {"quality": 90} if fmt == "JPEG" else {}
    if comment and fmt == "JPEG":
        kw["comment"] = comment
    img.save(b, fmt, **kw)
    return b.getvalue()


def link_family(client, senior: dict, child: dict, *, inviter: str = "child", senior_label: str | None = "엄마",
                child_label: str | None = "큰딸") -> int:
    """child 가 초대(또는 senior 가 초대)하고 상대가 수락 → linkId."""
    if inviter == "child":
        inv = client.post("/api/family/invites", headers=bearer(child), json={"myRole": "CHILD", "label": senior_label})
        assert inv.status_code == 201, inv.text
        acc = client.post("/api/family/invites/accept", headers=bearer(senior),
                          json={"code": inv.json()["code"], "label": child_label})
    else:
        inv = client.post("/api/family/invites", headers=bearer(senior), json={"myRole": "SENIOR", "label": child_label})
        assert inv.status_code == 201, inv.text
        acc = client.post("/api/family/invites/accept", headers=bearer(child),
                          json={"code": inv.json()["code"], "label": senior_label})
    assert acc.status_code == 200, acc.text
    return acc.json()["link"]["linkId"]
