"""가족 초대·수락·끊기: 한 번만, 만료, 번호 맞히기 제한, 권한, 감사 기록, 푸시."""
import re
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.auth.config import get_settings
from app.auth.tokens import sha256_hex
from app.family.models import FamilyInvite, FamilyLink, FamilyLog
from app.family.service import code_hash
from conftest import add_push_token, bearer, link_family, login_fake, pushes, run_db


def _invite(client, tokens, **body):
    r = client.post("/api/family/invites", headers=bearer(tokens), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _accept(client, tokens, **body):
    return client.post("/api/family/invites/accept", headers=bearer(tokens), json=body)


def _family(client, tokens):
    r = client.get("/api/family", headers=bearer(tokens))
    assert r.status_code == 200, r.text
    return r.json()


def _events():
    return [r.event_cd for r in run_db(lambda s: s.scalars(select(FamilyLog).order_by(FamilyLog.family_log_no)))]


def _token(inv: dict) -> str:
    return parse_qs(urlparse(inv["appLink"]).query)["t"][0]


def test_child_invites_and_senior_accepts_with_one_tap(client):
    child = login_fake(client, "c1:김지은", userType="CHILD")
    senior = login_fake(client, "s1:김순자")
    add_push_token(client, child, "child-phone")

    inv = _invite(client, child, myRole="CHILD", label="엄마")
    assert re.fullmatch(r"\d{6}", inv["code"])
    assert inv["myRole"] == "CHILD" and inv["expiresInSeconds"] == 1800
    assert inv["appLink"].startswith("ilgeodeurim://family/join?t=")
    assert inv["webLink"] == f"http://testserver/f/{_token(inv)}"
    assert f"{inv['code'][:3]} {inv['code'][3:]}" in inv["shareText"]

    # 번호·토큰 원문은 DB 에 없다
    row = run_db(lambda s: s.scalar(select(FamilyInvite)))
    assert row.code_hash == code_hash(get_settings().jwt_secret, inv["code"])
    assert row.code_hash != sha256_hex(inv["code"])  # 그냥 해시가 아니라 HMAC
    assert row.link_token_hash == sha256_hex(_token(inv))
    assert inv["code"] not in repr(row.__dict__)

    p = client.post("/api/family/invites/preview", headers=bearer(senior), json={"code": inv["code"]})
    assert p.status_code == 200, p.text
    assert p.json()["inviter"]["name"] == "김지은"
    assert p.json()["yourRole"] == "SENIOR" and p.json()["alreadyLinked"] is False

    # 띄어 쓴 번호도 받는다 (어르신이 들은 대로 넣어도)
    r = _accept(client, senior, code=f"{inv['code'][:3]} {inv['code'][3:]}", label="큰딸")
    assert r.status_code == 200, r.text
    link = r.json()["link"]
    assert link["myRole"] == "SENIOR"
    assert link["member"] == {"role": "CHILD", "name": "김지은", "label": "큰딸", "profileImageUrl": None}

    mine = _family(client, child)
    assert mine["pendingInvite"] is None
    assert mine["links"][0]["myRole"] == "CHILD"
    assert mine["links"][0]["member"]["label"] == "엄마" and mine["links"][0]["member"]["name"] == "김순자"

    msgs = pushes(client).to("child-phone")
    assert len(msgs) == 1 and msgs[0].data["type"] == "FAMILY_LINKED"
    assert msgs[0].body == "엄마와 연결됐어요."
    assert _events() == ["INVITE_CREATE", "INVITE_ACCEPT"]


def test_senior_invites_and_child_accepts_with_link_token(client):
    senior = login_fake(client, "s2:박영감")
    child = login_fake(client, "c2:박민수")
    inv = _invite(client, senior, myRole="SENIOR", label="아들")
    r = _accept(client, child, token=_token(inv), label="아버지")
    assert r.status_code == 200, r.text
    assert r.json()["link"]["myRole"] == "CHILD"
    assert r.json()["link"]["member"]["label"] == "아버지"
    row = run_db(lambda s: s.scalar(select(FamilyLink)))
    assert (row.senior_label, row.child_label) == ("아버지", "아들")
    assert row.senior_user_no == senior["user"]["userNo"] and row.child_user_no == child["user"]["userNo"]


def test_role_defaults_to_user_type(client):
    child = login_fake(client, "c3", userType="CHILD")
    assert _invite(client, child)["myRole"] == "CHILD"
    senior = login_fake(client, "s3")
    assert _invite(client, senior)["myRole"] == "SENIOR"


def test_invite_is_single_use(client):
    child = login_fake(client, "c4")
    senior = login_fake(client, "s4")
    other = login_fake(client, "x4")
    inv = _invite(client, child, myRole="CHILD")
    assert _accept(client, senior, code=inv["code"]).status_code == 200
    for body in ({"code": inv["code"]}, {"token": _token(inv)}):
        r = _accept(client, other, **body)
        assert r.status_code == 404 and r.json()["error"]["code"] == "invite_invalid"
    assert len(_family(client, other)["links"]) == 0


def test_invite_expires(client, env):
    env.set(FAMILY_INVITE_TTL_MIN="0")
    child = login_fake(client, "c5")
    senior = login_fake(client, "s5")
    inv = _invite(client, child, myRole="CHILD")
    r = _accept(client, senior, code=inv["code"])
    assert r.status_code == 404 and "시간이 지났어요" in r.json()["error"]["userMessage"]


def test_new_invite_cancels_the_previous_one(client):
    child = login_fake(client, "c6")
    senior = login_fake(client, "s6")
    first = _invite(client, child, myRole="CHILD")
    second = _invite(client, child, myRole="CHILD")
    assert _family(client, child)["pendingInvite"]["inviteId"] == second["inviteId"]
    assert _accept(client, senior, token=_token(first)).status_code == 404
    assert _accept(client, senior, code=second["code"]).status_code == 200


def test_only_inviter_can_cancel(client):
    child = login_fake(client, "c7")
    senior = login_fake(client, "s7")
    inv = _invite(client, child, myRole="CHILD")
    assert client.delete(f"/api/family/invites/{inv['inviteId']}", headers=bearer(senior)).status_code == 404
    assert client.delete(f"/api/family/invites/{inv['inviteId']}", headers=bearer(child)).status_code == 204
    assert _accept(client, senior, code=inv["code"]).status_code == 404


def test_cannot_accept_own_invite(client):
    child = login_fake(client, "c8")
    inv = _invite(client, child, myRole="CHILD")
    r = _accept(client, child, code=inv["code"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "invite_self"


def test_already_linked_in_either_direction(client):
    senior = login_fake(client, "s9")
    child = login_fake(client, "c9")
    link_family(client, senior, child)
    again = _invite(client, child, myRole="CHILD")
    assert _accept(client, senior, code=again["code"]).json()["error"]["code"] == "already_linked"
    reverse = _invite(client, senior, myRole="CHILD")  # 역할을 거꾸로 해도 같은 두 사람
    r = _accept(client, child, code=reverse["code"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_linked"
    p = client.post("/api/family/invites/preview", headers=bearer(child), json={"code": reverse["code"]})
    assert p.json()["alreadyLinked"] is True


def test_guessing_codes_is_rate_limited_per_user(client, env):
    env.set(FAMILY_FAIL_LIMIT="3")
    child = login_fake(client, "c10")
    attacker = login_fake(client, "x10")
    inv = _invite(client, child, myRole="CHILD")
    wrong = f"{(int(inv['code']) + 1) % 1000000:06d}"
    for _ in range(2):
        assert _accept(client, attacker, code=wrong).status_code == 404
    assert client.post("/api/family/invites/preview", headers=bearer(attacker),
                       json={"code": wrong}).status_code == 404
    r = _accept(client, attacker, code=inv["code"])  # 맞는 번호여도 잠깐 막힌다
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"
    assert _events().count("INVITE_FAIL") == 3


def test_guessing_codes_is_rate_limited_per_ip(client, env):
    env.set(FAMILY_FAIL_LIMIT_IP="2")
    a = login_fake(client, "x11a")
    b = login_fake(client, "x11b")
    for _ in range(2):
        assert _accept(client, a, code="000000").status_code in (404,)
    assert _accept(client, b, code="000001").status_code == 429


def test_bad_input(client):
    u = login_fake(client, "x12")
    r = _accept(client, u)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invite_missing"
    assert _accept(client, u, code="12ab56").status_code == 404
    assert _accept(client, u, token="short").status_code == 404
    assert _accept(client, u, token="a" * 101).status_code == 422


def test_family_size_limit(client, env):
    env.set(FAMILY_MAX_SENIORS="1")
    child = login_fake(client, "c13")
    link_family(client, login_fake(client, "s13a"), child)
    inv = _invite(client, login_fake(client, "s13b"), myRole="SENIOR")
    r = _accept(client, child, code=inv["code"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "family_limit"


def test_withdrawn_inviter_invite_is_dead(client):
    child = login_fake(client, "c14")
    senior = login_fake(client, "s14")
    inv = _invite(client, child, myRole="CHILD")
    assert client.delete("/api/me", headers=bearer(child)).status_code == 200
    assert _accept(client, senior, code=inv["code"]).status_code == 404


def test_either_side_can_unlink(client):
    senior = login_fake(client, "s15")
    child = login_fake(client, "c15")
    link_no = link_family(client, senior, child)
    assert client.delete(f"/api/family/links/{link_no}", headers=bearer(senior)).status_code == 204
    assert _family(client, child)["links"] == []
    assert client.delete(f"/api/family/links/{link_no}", headers=bearer(child)).status_code == 404

    link_no = link_family(client, senior, child)  # 다시 연결할 수 있다
    assert client.delete(f"/api/family/links/{link_no}", headers=bearer(child)).status_code == 204
    assert _family(client, senior)["links"] == []
    row = run_db(lambda s: s.get(FamilyLink, link_no))
    assert row.status_cd == "UNLINKED" and row.unlinked_by_user_no == child["user"]["userNo"]
    assert "LINK_UNLINK" in _events()


def test_strangers_cannot_touch_a_link(client):
    link_no = link_family(client, login_fake(client, "s16"), login_fake(client, "c16"))
    stranger = login_fake(client, "x16")
    assert client.delete(f"/api/family/links/{link_no}", headers=bearer(stranger)).json()["error"]["code"] \
        == "link_not_found"
    assert client.patch(f"/api/family/links/{link_no}", headers=bearer(stranger),
                        json={"label": "해커"}).status_code == 404
    assert run_db(lambda s: s.get(FamilyLink, link_no)).status_cd == "ACTIVE"


def test_label_changes_only_my_side(client):
    senior = login_fake(client, "s17")
    child = login_fake(client, "c17")
    link_no = link_family(client, senior, child)
    r = client.patch(f"/api/family/links/{link_no}", headers=bearer(senior), json={"label": "  막내\u0000 "})
    assert r.status_code == 200 and r.json()["link"]["member"]["label"] == "막내"
    assert _family(client, child)["links"][0]["member"]["label"] == "엄마"


def test_family_endpoints_need_login(client):
    assert client.post("/api/family/invites", json={}).status_code == 401
    assert client.post("/api/family/invites/accept", json={"code": "123456"}).status_code == 401
    assert client.get("/api/family").status_code == 401
    assert client.delete("/api/family/links/1").status_code == 401


def test_invite_page_opens_app_without_touching_db(client):
    child = login_fake(client, "c18")
    inv = _invite(client, child, myRole="CHILD")
    r = client.get(f"/f/{_token(inv)}")
    assert r.status_code == 200
    assert inv["appLink"] in r.text and "앱에서 열기" in r.text
    assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] == "no-referrer"
    assert client.get("/f/%3Cscript%3E").status_code == 404
    assert client.get(f"/f/{'b' * 43}").status_code == 200  # 모르는 토큰도 같은 페이지 (맞는지 알려 주지 않는다)
