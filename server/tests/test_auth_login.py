"""모바일 로그인: POST /api/auth/{kakao,google,fake} — 제공자 확인, 가입·연결, 응답 모양."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import User, UserAccess, UserLoginLog, UserOAuth
from app.auth.tokens import sha256_hex

from conftest import GOOGLE_ANDROID, KAKAO_APP_ID, bearer, google_claims, kakao_me, login_fake, run_db


def test_kakao_login_creates_user_then_reuses(client, http):
    r = client.post("/api/auth/kakao", json={"accessToken": "kakao-good", "deviceId": "dev-1", "deviceOs": "android"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["tokenType"] == "Bearer" and j["isNewUser"] is True
    assert j["accessTokenExpiresIn"] in (899, 900) and j["refreshTokenExpiresIn"] > 59 * 86400
    assert j["user"]["name"] == "박영감" and j["user"]["userType"] == "SENIOR"
    assert j["user"]["providers"] == ["KAKAO"] and j["user"]["email"] is None
    assert r.headers["cache-control"] == "no-store"
    # 다른 앱 토큰을 막으려고 access_token_info 로 app_id 를 먼저 본다
    info = http.hits("/v1/user/access_token_info")[0]
    assert info.headers["authorization"] == "Bearer kakao-good"

    r2 = client.post("/api/auth/kakao", json={"accessToken": "kakao-good"})
    assert r2.json()["isNewUser"] is False and r2.json()["user"]["userNo"] == j["user"]["userNo"]

    rows = run_db(lambda s: s.scalars(select(UserAccess)))
    rows = list(rows)
    assert len(rows) == 2 and rows[0].device_id == "dev-1" and rows[0].device_os == "ANDROID"
    # 토큰 원문은 DB 에 없다
    assert rows[0].refresh_token_hash == sha256_hex(j["refreshToken"])
    assert all(j["refreshToken"] not in (r.refresh_token_hash, r.access_jti) for r in rows)
    events = [l.event_cd for l in run_db(lambda s: s.scalars(select(UserLoginLog).order_by(UserLoginLog.login_log_no)))]
    assert events == ["SIGNUP", "LOGIN", "LOGIN"]


def test_kakao_verified_email_is_kept(client, http):
    http.kakao_tokens["kakao-mail"] = {"id": 2002, "app_id": int(KAKAO_APP_ID), "me": kakao_me(2002, email="p@k.com")}
    j = client.post("/api/auth/kakao", json={"accessToken": "kakao-mail", "userType": "CHILD"}).json()
    assert j["user"]["email"] == "p@k.com" and j["user"]["userType"] == "CHILD"


def test_kakao_token_from_other_app_rejected(client, http):
    http.kakao_tokens["other-app"] = {"id": 3003, "app_id": 9999, "me": kakao_me(3003)}
    r = client.post("/api/auth/kakao", json={"accessToken": "other-app"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "kakao_app_mismatch"
    assert not http.hits("/v2/user/me")  # 회원 정보까지 가지 않는다
    assert run_db(lambda s: s.scalar(select(User))) is None
    fail = run_db(lambda s: s.scalar(select(UserLoginLog)))
    assert fail.event_cd == "LOGIN_FAIL" and fail.fail_reason == "kakao_app_mismatch" and not fail.success_yn


def test_kakao_bad_token_and_outage(client, http):
    r = client.post("/api/auth/kakao", json={"accessToken": "nope"})
    assert r.status_code == 401 and r.json()["error"]["userMessage"]
    assert r.headers["www-authenticate"].startswith("Bearer")
    http.kakao_status = 500
    assert client.post("/api/auth/kakao", json={"accessToken": "kakao-good"}).status_code == 502
    assert client.post("/api/auth/kakao", json={}).status_code == 400


def test_kakao_not_configured(client, env):
    env.mp.delenv("KAKAO_APP_ID")
    env.set()
    r = client.post("/api/auth/kakao", json={"accessToken": "kakao-good"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "kakao_not_configured"


def test_google_login(client, http):
    tok = http.key.sign(google_claims())
    r = client.post("/api/auth/google", json={"idToken": tok})
    assert r.status_code == 200, r.text
    u = r.json()["user"]
    assert u["email"] == "grandma@example.com" and u["providers"] == ["GOOGLE"] and u["name"] == "김순자"
    # 안드로이드 클라이언트 ID 로 나온 토큰도 받는다 (GOOGLE_CLIENT_IDS)
    r2 = client.post("/api/auth/google", json={"idToken": http.key.sign(google_claims(aud=GOOGLE_ANDROID))})
    assert r2.json()["user"]["userNo"] == u["userNo"]


def test_google_rejects_foreign_audience(client, http):
    r = client.post("/api/auth/google", json={"idToken": http.key.sign(google_claims(aud="evil.apps.googleusercontent.com"))})
    assert r.status_code == 401 and r.json()["error"]["code"] == "id_token_bad_aud"


def test_same_email_different_provider_is_not_merged(client, http):
    """AsOne 은 이메일로 기존 회원을 찾았다. 여기서는 제공자 ID 로만 찾는다(남의 이메일로 계정 탈취 방지)."""
    http.kakao_tokens["kakao-mail"] = {"id": 2002, "app_id": int(KAKAO_APP_ID),
                                       "me": kakao_me(2002, email="grandma@example.com")}
    a = client.post("/api/auth/kakao", json={"accessToken": "kakao-mail"}).json()["user"]
    b = client.post("/api/auth/google", json={"idToken": http.key.sign(google_claims())}).json()["user"]
    assert a["userNo"] != b["userNo"]
    links = list(run_db(lambda s: s.scalars(select(UserOAuth))))
    assert {(l.oauth_provider_cd, l.oauth_id) for l in links} == {("KAKAO", "2002"), ("GOOGLE", "g-sub-1")}


def test_fake_provider_only_when_enabled(client, env):
    t = login_fake(client, "e2e", deviceId="d")
    assert client.get("/probe/me", headers=bearer(t)).json()["userNo"] == t["user"]["userNo"]
    env.mp.delenv("AUTH_FAKE_PROVIDER")
    env.set()
    r = client.post("/api/auth/fake", json={"accessToken": "fake:e2e"})
    assert r.status_code == 404


def test_unknown_provider_is_422(client):
    assert client.post("/api/auth/naver", json={"accessToken": "x"}).status_code == 422


def test_main_app_mounts_auth_routes(env):
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/auth/fake", json={"accessToken": "fake:main"})
        assert r.status_code == 200 and r.json()["user"]["providers"] == ["FAKE"]
        assert c.post("/api/auth/refresh", json={"refreshToken": r.json()["refreshToken"]}).status_code == 200
