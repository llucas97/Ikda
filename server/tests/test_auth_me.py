"""내 정보, 푸시 토큰, /api/analyze 선택 인증."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.models import UserPushToken
from app.main import app as main_app
from conftest import bearer, login_fake, run_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _rows():
    return list(run_db(lambda s: s.scalars(select(UserPushToken).order_by(UserPushToken.push_token_no))))


def test_me_requires_login_and_returns_profile(client):
    assert client.get("/api/me").status_code == 401
    t = login_fake(client, "me-1")
    r = client.get("/api/me", headers=bearer(t))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["userNo"] == t["user"]["userNo"]
    assert j["userType"] == "SENIOR"
    assert j["providers"] == ["FAKE"]
    assert j["createdAt"].endswith("Z")
    assert "T" in j["createdAt"]


def test_me_rejects_after_withdraw(client):
    t = login_fake(client, "me-gone")
    assert client.delete("/api/me", headers=bearer(t)).status_code == 200
    r = client.get("/api/me", headers=bearer(t))
    assert r.status_code == 401
    assert r.json()["error"]["code"] in {"session_revoked", "user_inactive"}


def test_push_token_upsert_and_deactivate_others(client):
    a = login_fake(client, "push-a")
    b = login_fake(client, "push-b")
    assert client.post("/api/me/push-token", json={"pushToken": "tok", "platform": "IOS"}).status_code == 401

    assert client.post("/api/me/push-token", headers=bearer(a),
                       json={"pushToken": "shared", "platform": "ios", "deviceId": "phone-a"}).status_code == 204
    assert client.post("/api/me/push-token", headers=bearer(a),
                       json={"pushToken": "shared", "platform": "android", "deviceId": "phone-a2"}).status_code == 204
    rows = _rows()
    assert len(rows) == 1
    assert rows[0].user_no == a["user"]["userNo"]
    assert rows[0].platform_cd == "ANDROID"
    assert rows[0].device_id == "phone-a2"
    assert rows[0].active_yn is True

    assert client.post("/api/me/push-token", headers=bearer(b),
                       json={"pushToken": "shared", "platform": "WEB"}).status_code == 204
    rows = _rows()
    assert len(rows) == 2
    by_user = {row.user_no: row for row in rows}
    assert by_user[a["user"]["userNo"]].active_yn is False
    mine = by_user[b["user"]["userNo"]]
    assert mine.active_yn is True and mine.platform_cd == "WEB"
    assert run_db(lambda s: s.scalar(select(func.count()).select_from(UserPushToken))) == 2


def _analyze(headers=None):
    return TestClient(main_app).post(
        "/api/analyze", headers=headers, files=[("images", ("bill.png", PNG, "image/png"))])


def test_analyze_open_when_flag_off(client):
    r = _analyze()
    assert r.status_code == 200, r.text
    assert r.json()["docType"] == "bill"


def test_analyze_requires_login_when_flag_on(client, env):
    env.set(AUTH_REQUIRED_FOR_ANALYZE="1")
    r = _analyze()
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "login_required"

    t = login_fake(client, "analyze-ok")
    ok = _analyze(bearer(t))
    assert ok.status_code == 200, ok.text


def test_analyze_rejects_bad_token_even_if_flag_off(client):
    r = _analyze({"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"
