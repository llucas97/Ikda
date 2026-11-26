"""ct_user_family: 수락하면 양쪽 줄, 관계·별명, 권한 깃발, 끊으면 둘 다 논리삭제."""
from sqlalchemy import select

from app.family.models import UserFamily
from conftest import bearer, login_fake, pushes, run_db
from test_family_documents import _send
from test_family_invite import _accept, _invite


def _rows():
    return list(run_db(lambda s: s.scalars(select(UserFamily).order_by(UserFamily.family_mapping_no))))


def test_accept_creates_both_directions_with_inverse_relations(client):
    child = login_fake(client, "c1:김지은", userType="CHILD")
    senior = login_fake(client, "s1:김순자")
    inv = _invite(client, child, myRole="CHILD", label="어머니", relationCd="MOTHER",
                  counterRelationCd="DAUGHTER", counterNickname="큰딸")
    r = _accept(client, senior, code=inv["code"], label="큰딸", relationCd="DAUGHTER")
    assert r.status_code == 200, r.text
    link = r.json()["link"]
    assert link["relationCd"] == "DAUGHTER" and link["nickname"] == "큰딸"
    assert link["relationLabel"] == "딸" and link["isPrimary"] is True
    assert link["permissions"]["canEdit"] is True  # 큰딸이 대신 보낼 수 있다

    child_view = client.get("/api/family", headers=bearer(child)).json()["links"][0]
    assert child_view["relationCd"] == "MOTHER" and child_view["nickname"] == "어머니"
    assert child_view["isPrimary"] is False and child_view["permissions"]["canEdit"] is False

    rows = {(row.primary_user_no, row.family_user_no): row for row in _rows()}
    assert len(rows) == 2
    senior_row = rows[(senior["user"]["userNo"], child["user"]["userNo"])]
    child_row = rows[(child["user"]["userNo"], senior["user"]["userNo"])]
    assert senior_row.relation_cd == "DAUGHTER" and senior_row.nickname == "큰딸"
    assert child_row.relation_cd == "MOTHER" and child_row.nickname == "어머니"
    assert senior_row.can_edit_yn is True and child_row.can_edit_yn is False


def test_label_without_code_is_guessed_and_primary_can_toggle(client):
    child = login_fake(client, "c2:박민수", userType="CHILD")
    senior = login_fake(client, "s2:박영감")
    inv = _invite(client, senior, myRole="SENIOR", label="아들")
    link_id = _accept(client, child, token=inv["appLink"].split("t=")[1], label="아버지").json()["link"]["linkId"]
    mine = client.get("/api/family", headers=bearer(senior)).json()["links"][0]
    assert mine["relationCd"] == "SON" and mine["nickname"] == "아들"
    theirs = client.get("/api/family", headers=bearer(child)).json()["links"][0]
    assert theirs["relationCd"] == "FATHER"

    # 자녀는 대표가 아니라 권한을 못 바꾼다
    r = client.patch(f"/api/family/links/{link_id}/permissions", headers=bearer(child), json={"canEdit": False})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_primary"

    r = client.patch(f"/api/family/links/{link_id}/permissions", headers=bearer(senior),
                     json={"canEdit": False, "notification": False})
    assert r.status_code == 200, r.text
    assert r.json()["link"]["permissions"]["canEdit"] is False
    assert r.json()["link"]["permissions"]["notification"] is False

    denied = _send(client, child, link_id)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "cannot_edit"

    # 알림을 끄면 다시 켜도 되기 전에, 보내기는 막혀 있다. 관계만 바꾼다.
    renamed = client.patch(f"/api/family/links/{link_id}", headers=bearer(senior),
                           json={"relationCd": "GRANDCHILD", "label": "손주"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["link"]["relationCd"] == "GRANDCHILD"
    assert renamed.json()["link"]["nickname"] == "손주"
    assert renamed.json()["link"]["permissions"]["canEdit"] is False


def test_unlink_soft_deletes_both_rows(client):
    child = login_fake(client, "c3", userType="CHILD")
    senior = login_fake(client, "s3")
    inv = _invite(client, child, myRole="CHILD", label="엄마")
    link_id = _accept(client, senior, code=inv["code"], label="딸").json()["link"]["linkId"]
    assert client.delete(f"/api/family/links/{link_id}", headers=bearer(child)).status_code == 204
    rows = _rows()
    assert len(rows) == 2 and all(row.deleted_yn and row.is_active is False for row in rows)


def test_notification_off_stores_document_without_push(client):
    child = login_fake(client, "c4:김지은", userType="CHILD")
    senior = login_fake(client, "s4:김순자")
    from conftest import add_push_token
    add_push_token(client, senior, "mom-phone")
    inv = _invite(client, child, myRole="CHILD", label="엄마")
    link_id = _accept(client, senior, code=inv["code"], label="큰딸").json()["link"]["linkId"]
    pushes(client).sent.clear()
    client.patch(f"/api/family/links/{link_id}/permissions", headers=bearer(senior), json={"notification": False})
    r = _send(client, child, link_id)
    assert r.status_code == 201, r.text
    assert r.json()["pushed"] == 0
    assert pushes(client).to("mom-phone") == []


def test_spouse_can_send_both_ways(client):
    a = login_fake(client, "p1:김순자")
    b = login_fake(client, "p2:김영수")
    inv = _invite(client, a, myRole="SENIOR", label="배우자", relationCd="SPOUSE", counterRelationCd="SPOUSE")
    link_id = _accept(client, b, code=inv["code"], label="배우자", relationCd="SPOUSE").json()["link"]["linkId"]
    assert _send(client, b, link_id).status_code == 201
    # 어르신 역할이라도 배우자 줄은 can_edit 가 켜져 있어 반대도 된다
    assert _send(client, a, link_id).status_code == 201


def test_bad_relation_code(client):
    user = login_fake(client, "u9")
    r = client.post("/api/family/invites", headers=bearer(user), json={"relationCd": "BOSS"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_relation"
