"""서류 보관·동기화·권한·자녀가 대신 보내기·자녀에게 나누기. 사진은 어디에도 남지 않는다."""
import base64
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import analysis
from app.family.models import Document, DocumentShare, DocumentTodo, FamilyLog
from app.main import app as main_app
from app.providers.fake import FakeProvider
from conftest import PNG, add_push_token, bearer, doc_image, link_family, login_fake, pushes, run_db


class CountingProvider(FakeProvider):
    def __init__(self):
        self.calls = 0

    async def classify(self, images, model):
        self.calls += 1
        return await super().classify(images, model)


@pytest.fixture
def provider(monkeypatch):
    p = CountingProvider()
    monkeypatch.setattr(analysis, "get_provider", lambda: p)
    return p


def _files(name="bill.png", data=PNG, mime="image/png"):
    return [("images", (name, data, mime))]


def _analyze_save(tokens, save=True, **kw):
    return TestClient(main_app).post("/api/analyze", headers=bearer(tokens) if tokens else None,
                                     data={"save": "true" if save else "false"}, files=_files(**kw))


def _send(client, tokens, link_no, **kw):
    return client.post(f"/api/family/links/{link_no}/analyze", headers=bearer(tokens), files=_files(**kw))


def _docs(client, tokens, **params):
    r = client.get("/api/documents", headers=bearer(tokens), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _events():
    return [r.event_cd for r in run_db(lambda s: s.scalars(select(FamilyLog).order_by(FamilyLog.family_log_no)))]


def _count(model):
    return run_db(lambda s: s.scalar(select(func.count()).select_from(model)))


@pytest.fixture
def family(client):
    senior = login_fake(client, "s1:김순자")
    child = login_fake(client, "c1:김지은", userType="CHILD")
    link_no = link_family(client, senior, child, senior_label="엄마", child_label="큰딸")
    add_push_token(client, senior, "mom-phone")
    add_push_token(client, child, "daughter-phone")
    pushes(client).sent.clear()
    return senior, child, link_no


# ---------- 본인 서류 ----------

def test_analyze_save_stores_result_for_logged_in_user(client):
    me = login_fake(client, "u1")
    r = _analyze_save(me)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["saved"] is True and body["id"].startswith("doc_")
    assert body["source"] == "SELF" and body["access"] == "OWNER" and body["seen"] is True
    assert body["docType"] == "bill" and body["todos"][0]["title"] == "전기요금 내기"

    listed = _docs(client, me)
    assert [d["id"] for d in listed["documents"]] == [body["id"]]
    assert listed["deleted"] == [] and listed["serverTime"].endswith("Z")


def test_analyze_save_without_login_saves_nothing(client):
    r = _analyze_save(None)
    assert r.status_code == 200 and r.json()["saved"] is False
    me = login_fake(client, "u2")
    assert _analyze_save(me, save=False).json().get("saved") is None
    assert _count(Document) == 0


def test_documents_need_login(client):
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/documents", json={"title": "x"}).status_code == 401


def test_import_is_idempotent_and_never_overwrites_others(client):
    a = login_fake(client, "u3")
    b = login_fake(client, "u4")
    body = {"id": "doc_local123abc", "docType": "publicNotice", "title": "주민센터 안내", "oneLiner": "한 줄",
            "todos": [{"id": "t1", "title": "서류 내기", "dueDate": "2026-12-01", "done": True},
                      {"id": "t1", "title": "같은 ID", "dueDate": "아무때나"}],
            "createdAt": "2026-11-01T09:00:00Z"}
    r1 = client.post("/api/documents", headers=bearer(a), json=body)
    assert r1.status_code == 201, r1.text
    doc = r1.json()
    assert doc["id"] == "doc_local123abc" and doc["docType"] == "government" and doc["source"] == "IMPORT"
    assert doc["createdAt"] == "2026-11-01T09:00:00Z"
    assert doc["todos"][0] == {"id": "t1", "title": "서류 내기", "dueDate": "2026-12-01", "detail": None,
                               "done": True, "remind": True}
    assert doc["todos"][1]["id"] != "t1" and doc["todos"][1]["dueDate"] is None

    again = client.post("/api/documents", headers=bearer(a), json=body)
    assert again.status_code == 200 and again.json()["id"] == "doc_local123abc"

    # 남이 같은 ID 로 올리면 새 ID 를 받고, a 의 서류는 그대로
    other = client.post("/api/documents", headers=bearer(b), json={**body, "title": "덮어쓰기"})
    assert other.status_code == 201 and other.json()["id"] != "doc_local123abc"
    assert client.get("/api/documents/doc_local123abc", headers=bearer(a)).json()["title"] == "주민센터 안내"
    assert _count(Document) == 2

    weird = client.post("/api/documents", headers=bearer(a), json={"id": "../../etc", "title": "t"})
    assert weird.status_code == 201 and weird.json()["id"].startswith("doc_")


def test_sync_since_returns_changes_and_tombstones(client):
    me = login_fake(client, "u5")
    first = client.post("/api/documents", headers=bearer(me),
                        json={"title": "하나", "todos": [{"id": "t1", "title": "할 일"}]}).json()
    second = client.post("/api/documents", headers=bearer(me), json={"title": "둘"}).json()
    mark = _docs(client, me)["serverTime"]
    assert _docs(client, me, since=mark)["documents"] == []

    r = client.patch(f"/api/documents/{first['id']}/todos/t1", headers=bearer(me), json={"done": True})
    assert r.status_code == 200 and r.json()["done"] is True
    assert client.delete(f"/api/documents/{second['id']}", headers=bearer(me)).status_code == 204

    changed = _docs(client, me, since=mark)
    assert [d["id"] for d in changed["documents"]] == [first["id"]]
    assert changed["documents"][0]["todos"][0]["done"] is True
    assert changed["deleted"] == [second["id"]]
    assert [d["id"] for d in _docs(client, me)["documents"]] == [first["id"]]
    assert client.get(f"/api/documents/{second['id']}", headers=bearer(me)).status_code == 404

    gone = run_db(lambda s: s.scalar(select(Document).where(Document.document_uid == second["id"])))
    assert gone.deleted_yn is True and gone.title is None and gone.details == []


def test_strangers_get_404_and_are_audited(client):
    owner = login_fake(client, "u6")
    stranger = login_fake(client, "x6")
    doc = client.post("/api/documents", headers=bearer(owner),
                      json={"title": "비밀", "todos": [{"id": "t1", "title": "할 일"}]}).json()
    for call in (lambda: client.get(f"/api/documents/{doc['id']}", headers=bearer(stranger)),
                 lambda: client.patch(f"/api/documents/{doc['id']}/todos/t1", headers=bearer(stranger),
                                      json={"done": True}),
                 lambda: client.delete(f"/api/documents/{doc['id']}", headers=bearer(stranger)),
                 lambda: client.post(f"/api/documents/{doc['id']}/shares", headers=bearer(stranger), json={})):
        r = call()
        assert r.status_code == 404 and r.json()["error"]["code"] == "document_not_found"
    assert client.get("/api/documents/doc_doesnotexist", headers=bearer(stranger)).status_code == 404
    assert _events().count("ACCESS_DENIED") == 4  # 없는 서류는 기록하지 않는다
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(owner)).json()["todos"][0]["done"] is False


# ---------- 자녀가 대신 보내기 ----------

def test_child_sends_on_behalf_of_parent(client, family, provider):
    senior, child, link_no = family
    r = _send(client, child, link_no, name="hospital.png")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["docType"] == "hospital" and doc["source"] == "FAMILY" and doc["access"] == "FAMILY"
    assert doc["sentBy"] == {"linkId": link_no, "label": "큰딸"}
    assert doc["owner"] == {"label": "엄마"} and doc["seen"] is False and doc["pushed"] == 1
    assert provider.calls == 1

    row = run_db(lambda s: s.scalar(select(Document)))
    assert row.owner_user_no == senior["user"]["userNo"] and row.sender_user_no == child["user"]["userNo"]

    # 어르신에게 푸시 — 잠금 화면에 제목·금액은 안 보인다
    msgs = pushes(client).to("mom-phone")
    assert len(msgs) == 1 and pushes(client).to("daughter-phone") == []
    m = msgs[0]
    assert m.title == "자녀가 서류를 보냈어요"
    assert m.body == "큰딸이 병원 안내를 보냈어요. 눌러서 확인해 주세요."
    assert m.data == {"type": "DOC_RECEIVED", "documentId": doc["id"], "linkId": str(link_no)}
    assert "건강검진" not in m.body

    # 어르신 목록에 '자녀가 보냄'으로 보이고, 열어 보면 seen
    mine = _docs(client, senior)["documents"]
    assert mine[0]["id"] == doc["id"] and mine[0]["sentBy"]["label"] == "큰딸" and mine[0]["seen"] is False
    assert client.post(f"/api/documents/{doc['id']}/seen", headers=bearer(senior)).status_code == 204
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(senior)).json()["seen"] is True

    # 자녀는 자기가 보낸 것을 볼 수 있지만 바꿀 수는 없다
    fam = client.get("/api/family/documents", headers=bearer(child)).json()["documents"]
    assert [d["id"] for d in fam] == [doc["id"]] and fam[0]["owner"]["label"] == "엄마"
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(child)).json()["access"] == "FAMILY"
    tid = doc["todos"][0]["id"]
    # can_edit_yn: 보낸 가족도 할 일(다 했어요·알림)을 고친다. 열어 봄 표시는 주인만.
    r = client.patch(f"/api/documents/{doc['id']}/todos/{tid}", headers=bearer(child), json={"done": True})
    assert r.status_code == 200, r.text
    assert r.json()["done"] is True
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(senior)).json()["todos"][0]["done"] is True
    assert client.post(f"/api/documents/{doc['id']}/seen", headers=bearer(child)).status_code == 403
    # 보낸 사람도 지울 수 있다. can_delete_yn 이 꺼져 있어도 보낸 사람은 예외.
    assert client.delete(f"/api/documents/{doc['id']}", headers=bearer(child)).status_code == 204
    assert _docs(client, child)["documents"] == []  # 자녀 '내 서류'에는 없다
    assert "DOC_SEND" in _events()


def test_senior_cannot_send_on_behalf(client, family, provider):
    senior, _, link_no = family
    r = _send(client, senior, link_no)
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_child"
    assert provider.calls == 0


def test_stranger_or_unlinked_cannot_send_and_ai_is_not_called(client, family, provider):
    senior, child, link_no = family
    stranger = login_fake(client, "x1")
    r = _send(client, stranger, link_no)
    assert r.status_code == 404 and r.json()["error"]["code"] == "link_not_found"
    assert _send(client, child, 999999).status_code == 404

    assert client.delete(f"/api/family/links/{link_no}", headers=bearer(senior)).status_code == 204
    assert _send(client, child, link_no).status_code == 404
    assert provider.calls == 0 and _count(Document) == 0


def test_daily_send_limit(client, env, family, provider):
    env.set(FAMILY_SEND_DAILY_LIMIT="2")
    _, child, link_no = family
    assert _send(client, child, link_no).status_code == 201
    assert _send(client, child, link_no).status_code == 201
    r = _send(client, child, link_no)
    assert r.status_code == 429 and r.json()["error"]["code"] == "send_limit"
    assert provider.calls == 2


def test_bad_photo_from_child_stores_nothing(client, family, provider):
    _, child, link_no = family
    r = _send(client, child, link_no, name="bill.jpg", data=doc_image(blur=6), mime="image/jpeg")
    assert r.status_code == 422 and r.json()["error"]["code"] == "photo_blurry"
    assert provider.calls == 0 and _count(Document) == 0 and pushes(client).sent == []


def test_send_without_push_token_still_stores(client, provider):
    senior = login_fake(client, "s2")
    child = login_fake(client, "c2")
    link_no = link_family(client, senior, child)
    r = _send(client, child, link_no)
    assert r.status_code == 201 and r.json()["pushed"] == 0
    assert len(_docs(client, senior)["documents"]) == 1


# ---------- 자녀에게 보내기 (나누기) ----------

def test_parent_shares_with_children(client, family):
    senior, child, link_no = family
    child2 = login_fake(client, "c1b:김민수")
    link2 = link_family(client, senior, child2, child_label="작은아들")
    add_push_token(client, child2, "son-phone")
    stranger = login_fake(client, "x2")
    pushes(client).sent.clear()

    doc = _analyze_save(senior, name="medicine.png").json()
    # 나누기 전에는 자녀도 못 본다
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(child)).status_code == 404

    r = client.post(f"/api/documents/{doc['id']}/shares", headers=bearer(senior), json={})
    assert r.status_code == 200, r.text
    got = {s["linkId"]: s for s in r.json()["sharedTo"]}
    assert got[link_no] == {"linkId": link_no, "label": "큰딸", "new": True, "pushed": 1}
    assert got[link2]["label"] == "작은아들" and got[link2]["new"] is True

    m = pushes(client).to("daughter-phone")[0]
    assert m.data["type"] == "DOC_SHARED" and m.data["documentId"] == doc["id"]
    assert m.title == "엄마가 서류를 보냈어요" and m.body.startswith("약 안내를 같이 봐 달래요")

    seen = client.get(f"/api/documents/{doc['id']}", headers=bearer(child)).json()
    assert seen["access"] == "FAMILY" and seen["owner"] == {"label": "엄마"} and seen["sentBy"] is None
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(stranger)).status_code == 404

    # 다시 눌러도 중복·중복 푸시 없음
    again = client.post(f"/api/documents/{doc['id']}/shares", headers=bearer(senior), json={"linkIds": [link_no]})
    assert again.json()["sharedTo"] == [{"linkId": link_no, "label": "큰딸", "new": False, "pushed": 0}]
    assert len(pushes(client).to("daughter-phone")) == 1
    assert _count(DocumentShare) == 2

    # 거두기
    assert client.delete(f"/api/documents/{doc['id']}/shares/{link_no}", headers=bearer(senior)).status_code == 204
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(child)).status_code == 404
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(child2)).status_code == 200
    assert {"DOC_SHARE", "DOC_UNSHARE"} <= set(_events())


def test_share_rules(client, family):
    senior, child, link_no = family
    own = client.post("/api/documents", headers=bearer(child), json={"title": "자녀 서류"}).json()
    r = client.post(f"/api/documents/{own['id']}/shares", headers=bearer(child), json={"linkIds": [link_no]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_senior"  # 자녀 → 어르신 방향은 '대신 보내기'
    r = client.post(f"/api/documents/{own['id']}/shares", headers=bearer(child), json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_family"

    sent = _send(client, child, link_no).json()
    r = client.post(f"/api/documents/{sent['id']}/shares", headers=bearer(child), json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only"

    lonely = login_fake(client, "s3")
    doc = client.post("/api/documents", headers=bearer(lonely), json={"title": "혼자"}).json()
    r = client.post(f"/api/documents/{doc['id']}/shares", headers=bearer(lonely), json={"linkIds": [link_no]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "link_not_found"


def test_deleting_a_shared_document_revokes_access(client, family):
    senior, child, _ = family
    doc = client.post("/api/documents", headers=bearer(senior), json={"title": "지울 서류"}).json()
    client.post(f"/api/documents/{doc['id']}/shares", headers=bearer(senior), json={})
    assert client.delete(f"/api/documents/{doc['id']}", headers=bearer(senior)).status_code == 204
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(child)).status_code == 404
    assert client.get("/api/family/documents", headers=bearer(child)).json()["documents"] == []
    assert run_db(lambda s: s.scalar(select(func.count()).select_from(DocumentShare)
                                     .where(DocumentShare.revoked_yn.is_(False)))) == 0


# ---------- 끊기·탈퇴 ----------

def test_unlink_cuts_off_access_but_parent_keeps_documents(client, family, provider):
    senior, child, link_no = family
    sent = _send(client, child, link_no).json()
    shared = client.post("/api/documents", headers=bearer(senior), json={"title": "나눈 것"}).json()
    client.post(f"/api/documents/{shared['id']}/shares", headers=bearer(senior), json={})

    assert client.delete(f"/api/family/links/{link_no}", headers=bearer(child)).status_code == 204
    for uid in (sent["id"], shared["id"]):
        assert client.get(f"/api/documents/{uid}", headers=bearer(child)).status_code == 404
    assert client.get("/api/family/documents", headers=bearer(child)).json()["documents"] == []
    mine = {d["id"]: d for d in _docs(client, senior)["documents"]}
    assert set(mine) == {sent["id"], shared["id"]}
    assert mine[sent["id"]]["sentBy"]["label"] == "큰딸"

    # 다시 연결해도 예전 나눔은 살아나지 않는다 (새로 나눠야 함)
    link_family(client, senior, child)
    assert client.get(f"/api/documents/{shared['id']}", headers=bearer(child)).status_code == 404


def test_senior_withdraw_removes_their_documents(client, family, provider):
    senior, child, link_no = family
    sent = _send(client, child, link_no).json()
    assert client.delete("/api/me", headers=bearer(senior)).status_code == 200
    assert _count(Document) == 0 and _count(DocumentTodo) == 0
    assert client.get(f"/api/documents/{sent['id']}", headers=bearer(child)).status_code == 404
    assert client.get("/api/family", headers=bearer(child)).json()["links"] == []


def test_child_withdraw_keeps_parent_documents_without_name(client, family, provider):
    senior, child, link_no = family
    sent = _send(client, child, link_no).json()
    assert client.delete("/api/me", headers=bearer(child)).status_code == 200
    doc = client.get(f"/api/documents/{sent['id']}", headers=bearer(senior)).json()
    assert doc["source"] == "FAMILY" and doc["sentBy"]["label"] == "자녀"
    assert client.get("/api/family", headers=bearer(senior)).json()["links"] == []


def test_parent_view_off_hides_documents_and_list_keeps_viewer_relation(client, family):
    """자녀의 부모님 서류는 주인 줄 can_view_yn 을 따른다. GET /api/family 관계는 보는 사람 기준."""
    senior, child, link_no = family
    doc = client.post("/api/documents", headers=bearer(senior), json={"title": "엄마 서류"}).json()
    assert client.post(f"/api/documents/{doc['id']}/shares", headers=bearer(senior), json={}).status_code == 200
    listed = client.get("/api/family/documents", headers=bearer(child)).json()["documents"]
    assert [d["id"] for d in listed] == [doc["id"]]
    assert listed[0]["owner"]["label"] == "엄마"

    r = client.patch(f"/api/family/links/{link_no}/permissions", headers=bearer(senior), json={"canView": False})
    assert r.status_code == 200, r.text
    assert r.json()["link"]["permissions"]["canView"] is False
    assert client.get("/api/family/documents", headers=bearer(child)).json()["documents"] == []
    assert client.get(f"/api/documents/{doc['id']}", headers=bearer(child)).status_code == 404

    child_link = client.get("/api/family", headers=bearer(child)).json()["links"][0]
    assert child_link["relationCd"] == "MOTHER" and child_link["relationLabel"] == "어머니"
    assert child_link["nickname"] == "엄마"
    senior_link = client.get("/api/family", headers=bearer(senior)).json()["links"][0]
    assert senior_link["relationCd"] == "DAUGHTER" and senior_link["relationLabel"] == "딸"
    assert senior_link["nickname"] == "큰딸"


# ---------- 사진은 남지 않는다 ----------

def test_uploaded_images_are_never_stored(client, family, provider, env):
    if os.getenv("TEST_DATABASE_URL"):
        pytest.skip("SQLite 파일을 직접 들여다보는 시험")
    senior, child, link_no = family
    marker = b"PRIVATE-PHOTO-MARKER-7f3a9c"
    img = doc_image(comment=marker)
    assert marker in img
    assert _send(client, child, link_no, name="bill.jpg", data=img, mime="image/jpeg").status_code == 201
    assert _analyze_save(senior, name="bill.jpg", data=img, mime="image/jpeg").status_code == 200

    db_path = os.environ["DATABASE_URL"].split("///", 1)[1]
    run_db(lambda s: s.commit())
    from app import db as dbmod
    import asyncio
    asyncio.run(dbmod.reset())  # 파일에 다 쓰이게 연결을 닫는다
    folder = os.path.dirname(db_path)
    raw = b"".join(open(os.path.join(folder, f), "rb").read() for f in os.listdir(folder)
                   if f.startswith(os.path.basename(db_path)))
    assert "한국전력 전기요금 고지서".encode() in raw  # 결과(글)는 있다 — 검사가 제대로 도는지 확인
    assert marker not in raw
    assert base64.b64encode(img)[200:260] not in raw
    assert img[2000:2064] not in raw
