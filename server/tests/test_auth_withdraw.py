"""탈퇴 DELETE /api/me: 카카오 연결 끊기, 세션·푸시 끊기, 개인정보 지우기, 다시 가입."""
from __future__ import annotations

from sqlalchemy import select

from app.auth.models import User, UserAccess, UserOAuth, UserPushToken

from conftest import bearer, google_claims, run_db


def kakao_login(client):
    r = client.post("/api/auth/kakao", json={"accessToken": "kakao-good"})
    assert r.status_code == 200, r.text
    return r.json()


async def _add_push(s, user_no):
    s.add(UserPushToken(user_no=user_no, push_token="fcm-x", platform_cd="IOS"))
    await s.commit()


def test_withdraw_with_admin_key(client, http, env):
    env.set(KAKAO_ADMIN_KEY="admin-key")
    t = kakao_login(client)
    uid = t["user"]["userNo"]
    run_db(lambda s: _add_push(s, uid))

    r = client.delete("/api/me", headers=bearer(t))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "unlinked": {"KAKAO": "OK"}}
    unlink = http.hits("/v1/user/unlink")[0]
    assert unlink.headers["authorization"] == "KakaoAK admin-key"
    assert b"target_id_type=user_id" in unlink.content and b"target_id=1001" in unlink.content

    user = run_db(lambda s: s.get(User, uid))
    assert user.status_cd == "WITHDRAW" and user.deleted_yn and user.withdraw_type_cd == "SELF"
    assert user.name is None and user.email is None and user.profile_image_url is None
    link = run_db(lambda s: s.scalar(select(UserOAuth)))
    assert link.deleted_yn and link.oauth_id is None and link.oauth_name is None and link.unlink_result_cd == "OK"
    assert all(a.revoked_yn and a.revoke_reason_cd == "WITHDRAW" for a in run_db(lambda s: s.scalars(select(UserAccess))))
    assert run_db(lambda s: s.scalar(select(UserPushToken))).active_yn is False

    # 남은 토큰은 모두 무효
    assert client.get("/probe/me", headers=bearer(t)).status_code == 401
    assert client.post("/api/auth/refresh", json={"refreshToken": t["refreshToken"]}).status_code == 401
    # 같은 카카오 계정으로 다시 오면 새 회원
    again = kakao_login(client)
    assert again["isNewUser"] is True and again["user"]["userNo"] != uid


def test_withdraw_with_user_kakao_token(client, http):
    t = kakao_login(client)
    r = client.request("DELETE", "/api/me", headers=bearer(t), json={"kakaoAccessToken": "kakao-good"})
    assert r.json()["unlinked"] == {"KAKAO": "OK"}
    assert http.hits("/v1/user/unlink")[0].headers["authorization"] == "Bearer kakao-good"


def test_withdraw_without_any_kakao_credential_skips_unlink(client, http):
    t = kakao_login(client)
    assert client.delete("/api/me", headers=bearer(t)).json()["unlinked"] == {"KAKAO": "SKIPPED"}
    assert not http.hits("/v1/user/unlink")


def test_withdraw_survives_kakao_failure(client, http, env):
    env.set(KAKAO_ADMIN_KEY="admin-key")
    t = kakao_login(client)
    http.unlink_status = 500
    r = client.delete("/api/me", headers=bearer(t))
    assert r.status_code == 200 and r.json()["unlinked"] == {"KAKAO": "FAILED"}
    assert run_db(lambda s: s.get(User, t["user"]["userNo"])).deleted_yn


def test_withdraw_google_user(client, http):
    t = client.post("/api/auth/google", json={"idToken": http.key.sign(google_claims())}).json()
    assert client.delete("/api/me", headers=bearer(t)).json()["unlinked"] == {"GOOGLE": "SKIPPED"}


def test_withdraw_requires_login(client):
    r = client.delete("/api/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "login_required"
