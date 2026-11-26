"""refresh 회전·재사용 탐지, access 토큰 확인, 로그아웃, 세션 수 제한."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update

from app.auth.models import UserAccess, UserLoginLog, UserPushToken
from app.db import utcnow

from conftest import bearer, login_fake, run_db


def refresh(client, token, **extra):
    return client.post("/api/auth/refresh", json={"refreshToken": token, **extra})


def code(r) -> str:
    return r.json()["error"]["code"]


def test_rotation_issues_new_pair_and_keeps_session(client):
    t1 = login_fake(client)
    r = refresh(client, t1["refreshToken"])
    assert r.status_code == 200, r.text
    t2 = r.json()
    assert t2["refreshToken"] != t1["refreshToken"] and t2["accessToken"] != t1["accessToken"]
    assert "isNewUser" not in t2 and t2["user"]["userNo"] == t1["user"]["userNo"]
    me1 = client.get("/probe/me", headers=bearer(t1)).json()
    me2 = client.get("/probe/me", headers=bearer(t2)).json()
    assert me1["sid"] == me2["sid"]  # 같은 세션(family)
    rows = list(run_db(lambda s: s.scalars(select(UserAccess).order_by(UserAccess.access_no))))
    assert rows[0].used_at is not None and rows[1].parent_access_no == rows[0].access_no
    assert rows[1].auth_at == rows[0].auth_at  # 처음 로그인 시각은 그대로


def test_reuse_within_grace_is_not_fatal(client):
    t1 = login_fake(client)
    t2 = refresh(client, t1["refreshToken"]).json()
    r = refresh(client, t1["refreshToken"])  # 앱이 동시에 두 번 보낸 경우
    assert r.status_code == 401 and code(r) == "refresh_superseded"
    assert refresh(client, t2["refreshToken"]).status_code == 200  # 새 토큰은 살아 있다


def test_reuse_after_grace_revokes_whole_family(client, env):
    env.set(REFRESH_REUSE_GRACE_S=0)
    t1 = login_fake(client)
    other = login_fake(client)  # 같은 회원의 다른 기기 세션은 건드리지 않는다
    t2 = refresh(client, t1["refreshToken"]).json()
    run_db(_age_used_at)

    r = refresh(client, t1["refreshToken"])  # 훔친 옛 토큰
    assert r.status_code == 401 and code(r) == "refresh_reused"
    assert code(refresh(client, t2["refreshToken"])) == "refresh_revoked"  # 정상 앱 쪽도 끊긴다
    r = client.get("/probe/me", headers=bearer(t2))  # 아직 안 끝난 access 도 바로 막힌다
    assert r.status_code == 401 and code(r) == "session_revoked"
    assert client.get("/probe/me", headers=bearer(other)).status_code == 200
    ev = run_db(lambda s: s.scalar(select(UserLoginLog).where(UserLoginLog.event_cd == "REUSE_DETECTED")))
    assert ev is not None and ev.user_no == t1["user"]["userNo"]
    reasons = {r.revoke_reason_cd for r in run_db(lambda s: s.scalars(select(UserAccess).where(UserAccess.revoked_yn)))}
    assert reasons == {"REUSE_DETECTED"}


async def _age_used_at(s):
    await s.execute(update(UserAccess).where(UserAccess.used_at.is_not(None))
                    .values(used_at=utcnow() - timedelta(minutes=5)))
    await s.commit()


def test_refresh_rejections(client, env):
    assert code(refresh(client, "never-issued")) == "invalid_refresh"
    assert client.post("/api/auth/refresh", json={"refreshToken": "x" * 500}).status_code == 422
    env.set(REFRESH_TOKEN_TTL_DAYS=0)
    t = login_fake(client)
    assert code(refresh(client, t["refreshToken"])) == "refresh_expired"


def test_session_absolute_lifetime(client, env):
    t = login_fake(client)

    async def old_login(s):
        await s.execute(update(UserAccess).values(auth_at=utcnow() - timedelta(days=400)))
        await s.commit()
    run_db(old_login)
    # refresh 자체는 아직 안 끝났어도 처음 로그인에서 365일이 지나면 다시 로그인
    assert code(refresh(client, t["refreshToken"])) == "refresh_expired"


def test_refresh_expiry_capped_by_session_max(client, env):
    env.set(SESSION_MAX_DAYS=10)
    t = login_fake(client)
    assert t["refreshTokenExpiresIn"] <= 10 * 86400  # 60일이 아니라 세션 최대 10일
    assert refresh(client, t["refreshToken"]).json()["refreshTokenExpiresIn"] <= 10 * 86400


def test_access_token_checks(client):
    assert code(client.get("/probe/me")) == "login_required"
    assert code(client.get("/probe/me", headers={"Authorization": "Bearer junk"})) == "invalid_token"
    assert code(client.get("/probe/me", headers={"Authorization": "Basic abc"})) == "login_required"


def test_logout_revokes_session(client):
    t = login_fake(client, deviceId="dev-9")
    run_db(lambda s: _add_push(s, t["user"]["userNo"], "dev-9"))
    r = client.post("/api/auth/logout", json={"refreshToken": t["refreshToken"], "deviceId": "dev-9"})
    assert r.status_code == 204
    assert code(refresh(client, t["refreshToken"])) == "refresh_revoked"
    assert code(client.get("/probe/me", headers=bearer(t))) == "session_revoked"
    push = run_db(lambda s: s.scalar(select(UserPushToken)))
    assert push.active_yn is False
    # 다시 해도, 모르는 토큰이어도 204 (있는지 없는지 알려 주지 않는다)
    assert client.post("/api/auth/logout", json={"refreshToken": t["refreshToken"]}).status_code == 204
    assert client.post("/api/auth/logout", json={"refreshToken": "unknown"}).status_code == 204
    assert client.post("/api/auth/logout").status_code == 204


async def _add_push(s, user_no, device_id):
    s.add(UserPushToken(user_no=user_no, push_token="fcm-1", platform_cd="ANDROID", device_id=device_id))
    await s.commit()


def test_logout_with_access_token_only(client):
    t = login_fake(client)
    assert client.post("/api/auth/logout", headers=bearer(t)).status_code == 204
    assert code(refresh(client, t["refreshToken"])) == "refresh_revoked"


def test_logout_cannot_revoke_someone_elses_session(client):
    mine = login_fake(client, "me")
    theirs = login_fake(client, "them")
    # 내 access 와 남의 refresh 를 같이 보내면 남의 세션은 그대로, 내 세션만 끊긴다
    client.post("/api/auth/logout", headers=bearer(mine), json={"refreshToken": theirs["refreshToken"]})
    assert refresh(client, theirs["refreshToken"]).status_code == 200
    assert code(refresh(client, mine["refreshToken"])) == "refresh_revoked"


def test_logout_all_devices(client):
    a = login_fake(client)
    b = login_fake(client)
    assert client.post("/api/auth/logout", json={"allDevices": True}).status_code == 401
    assert client.post("/api/auth/logout", json={"allDevices": True}, headers=bearer(a)).status_code == 204
    assert code(refresh(client, b["refreshToken"])) == "refresh_revoked"


def test_session_limit_drops_oldest(client, env):
    env.set(MAX_SESSIONS_PER_USER=2)
    s1, s2, s3 = (login_fake(client) for _ in range(3))
    assert code(refresh(client, s1["refreshToken"])) == "refresh_revoked"
    assert refresh(client, s2["refreshToken"]).status_code == 200
    assert refresh(client, s3["refreshToken"]).status_code == 200
