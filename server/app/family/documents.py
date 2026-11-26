"""서류 보관과 권한. 사진은 받지도 두지도 않는다 — AI 가 정리한 글만.

누가 무엇을 할 수 있나 (docs/phase3-plan.md §3):
  주인(owner_user_no)            읽기, 할 일 바꾸기, 열어 봄 표시, 지우기, 자녀에게 나누기·거두기
  연결된 자녀(ACTIVE, 둘 다 활성)  읽기만 — 자기가 보낸 서류 또는 주인이 나눠 준 서류
  그 밖                           404 (있는지도 알려 주지 않는다), 서류가 있으면 ACCESS_DENIED 감사 기록
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.models import User
from ..db import utcnow
from ..schema import DOC_TYPES, AnalysisResult, _clean_date
from .config import FamilySettings
from .errors import FamilyError, document_not_found
from .models import Document, DocumentShare, DocumentTodo, FamilyLink, UserFamily
from .service import (LinkView, active_link_between, audit, family_mapping, get_link_for, granted,
                      label_of_child, label_of_senior)

MAX_LIST = 1000
_UID_RE = re.compile(r"^doc_[A-Za-z0-9_-]{4,36}$")
_TODO_UID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def new_uid() -> str:
    return f"doc_{secrets.token_hex(10)}"


def iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _date(v: str | None) -> date | None:
    v = _clean_date(v)
    return date.fromisoformat(v) if v else None


def _strings(items: list[str], n: int, size: int) -> list[str]:
    return [str(x).strip()[:size] for x in items if str(x).strip()][:n]


# ---------- 앱 기기 저장본 올리기 (동기화) ----------

class TodoIn(BaseModel):
    id: str | None = Field(default=None, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    dueDate: str | None = None
    detail: str | None = Field(default=None, max_length=500)
    done: bool = False
    remind: bool = True


class DocumentIn(BaseModel):
    id: str | None = Field(default=None, max_length=60)
    docType: str = "other"
    title: str = Field(min_length=1, max_length=200)
    oneLiner: str = Field(default="", max_length=1000)
    amount: int | None = Field(default=None, ge=0, le=10 ** 13)
    dueDate: str | None = None
    todos: list[TodoIn] = Field(default_factory=list, max_length=30)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    details: list[str] = Field(default_factory=list, max_length=30)
    model: str | None = Field(default=None, max_length=100)
    createdAt: datetime | None = None

    @field_validator("docType", mode="before")
    @classmethod
    def _v_type(cls, v):
        if v == "publicNotice":  # 예전 앱 저장본
            return "government"
        return v if v in DOC_TYPES else "other"


# ---------- 만들기 ----------

def _todo_rows(todos: list[dict], now: datetime) -> list[DocumentTodo]:
    rows, seen = [], set()
    for i, t in enumerate(todos[:30]):
        tid = str(t.get("id") or "")
        if not _TODO_UID_RE.match(tid) or tid in seen:
            tid = f"t_{secrets.token_hex(4)}"
        seen.add(tid)
        rows.append(DocumentTodo(todo_uid=tid, title=str(t["title"])[:200], due_date=_date(t.get("dueDate")),
                                 detail=(str(t["detail"])[:500] if t.get("detail") else None),
                                 done_yn=bool(t.get("done", False)), remind_yn=bool(t.get("remind", True)),
                                 sort_order=i, done_at=now if t.get("done") else None, created_at=now, updated_at=now))
    return rows


async def _create(db: AsyncSession, data: dict, *, uid: str, owner: int, sender: int, source: str,
                  link_no: int | None = None, sender_label: str | None = None, page_count: int | None = None,
                  created_at: datetime | None = None) -> Document:
    now = utcnow()
    doc = Document(
        document_uid=uid, owner_user_no=owner, sender_user_no=sender, family_link_no=link_no,
        sender_label=sender_label, source_cd=source,
        doc_type_cd=data.get("docType") if data.get("docType") in DOC_TYPES else "other",
        title=str(data.get("title") or "서류")[:200], one_liner=str(data.get("oneLiner") or "")[:1000],
        amount=data.get("amount"), due_date=_date(data.get("dueDate")),
        warnings=_strings(data.get("warnings") or [], 20, 500), details=_strings(data.get("details") or [], 30, 500),
        model_cd=(str(data["model"])[:100] if data.get("model") else None), page_count=page_count,
        owner_seen_at=now if source != "FAMILY" else None,
        created_at=created_at if created_at and created_at.tzinfo else now, created_by=sender,
        updated_at=now, updated_by=sender,
    )
    db.add(doc)
    await db.flush()
    for t in _todo_rows(data.get("todos") or [], now):
        t.document_no = doc.document_no
        db.add(t)
    await db.flush()
    return doc


async def store_result(db: AsyncSession, user: User, result: AnalysisResult, *, page_count: int) -> Document:
    """본인이 찍은 결과를 보관 (/api/analyze save=true)."""
    doc = await _create(db, result.model_dump(), uid=new_uid(), owner=user.user_no, sender=user.user_no,
                        source="SELF", page_count=page_count)
    await db.commit()
    return doc


async def import_document(db: AsyncSession, user: User, body: DocumentIn) -> tuple[Document, bool]:
    """기기에만 있던 서류를 올린다. 같은 ID 를 두 번 올려도 하나만 생긴다."""
    if body.id and _UID_RE.match(body.id):
        existing = await db.scalar(select(Document).where(Document.document_uid == body.id))
        if existing is not None and existing.owner_user_no == user.user_no:
            return existing, False
        uid = body.id if existing is None else new_uid()  # 남의 ID 와 겹치면 새로 준다
    else:
        uid = new_uid()
    doc = await _create(db, body.model_dump(), uid=uid, owner=user.user_no, sender=user.user_no, source="IMPORT",
                        created_at=body.createdAt)
    await db.commit()
    return doc, True


# ---------- 읽기 ----------

async def todos_of(db: AsyncSession, doc_nos: list[int]) -> dict[int, list[DocumentTodo]]:
    out: dict[int, list[DocumentTodo]] = {n: [] for n in doc_nos}
    if not doc_nos:
        return out
    for t in await db.scalars(select(DocumentTodo).where(DocumentTodo.document_no.in_(doc_nos))
                              .order_by(DocumentTodo.document_no, DocumentTodo.sort_order, DocumentTodo.todo_no)):
        out[t.document_no].append(t)
    return out


def todo_json(t: DocumentTodo) -> dict:
    return {"id": t.todo_uid, "title": t.title, "dueDate": t.due_date.isoformat() if t.due_date else None,
            "detail": t.detail, "done": t.done_yn, "remind": t.remind_yn}


def document_json(doc: Document, todos: list[DocumentTodo], *, access: str, owner_label: str | None = None) -> dict:
    if doc.deleted_yn:
        return {"id": doc.document_uid, "deleted": True, "updatedAt": iso_utc(doc.updated_at)}
    out = {
        "id": doc.document_uid,
        "docType": doc.doc_type_cd,
        "title": doc.title,
        "oneLiner": doc.one_liner,
        "amount": doc.amount,
        "dueDate": doc.due_date.isoformat() if doc.due_date else None,
        "todos": [todo_json(t) for t in todos],
        "warnings": list(doc.warnings or []),
        "details": list(doc.details or []),
        "model": doc.model_cd,
        "createdAt": iso_utc(doc.created_at),
        "updatedAt": iso_utc(doc.updated_at),
        "source": doc.source_cd,
        "sentBy": ({"linkId": doc.family_link_no, "label": doc.sender_label or "자녀"}
                   if doc.source_cd == "FAMILY" else None),
        "seen": doc.owner_seen_at is not None,
        "access": access,
    }
    if owner_label is not None:
        out["owner"] = {"label": owner_label}
    return out


async def list_owned(db: AsyncSession, user_no: int, since: datetime | None) -> tuple[list[dict], list[str]]:
    q = select(Document).where(Document.owner_user_no == user_no)
    q = q.where(Document.updated_at >= since) if since else q.where(Document.deleted_yn.is_(False))
    docs = list(await db.scalars(q.order_by(Document.created_at.desc(), Document.document_no.desc()).limit(MAX_LIST)))
    live = [d for d in docs if not d.deleted_yn]
    todos = await todos_of(db, [d.document_no for d in live])
    return ([document_json(d, todos[d.document_no], access="OWNER") for d in live],
            [d.document_uid for d in docs if d.deleted_yn])


async def _family_link_for(db: AsyncSession, viewer_no: int, doc: Document) -> FamilyLink | None:
    """가족이 이 서류를 볼 수 있으면 그 연결. 보기 권한이 있고, 자기가 보냈거나 나눠 받았어야 한다."""
    link = await active_link_between(db, doc.owner_user_no, viewer_no)
    if link is None:
        return None
    owner = await db.get(User, doc.owner_user_no)
    viewer = await db.get(User, viewer_no)
    if owner is None or not owner.is_active or viewer is None or not viewer.is_active:
        return None
    if not await granted(db, doc.owner_user_no, viewer_no, "can_view_yn"):
        return None
    if doc.sender_user_no == viewer_no:
        return link
    shared = await db.scalar(select(DocumentShare.share_no).where(
        DocumentShare.document_no == doc.document_no, DocumentShare.shared_to_user_no == viewer_no,
        DocumentShare.revoked_yn.is_(False)).limit(1))
    return link if shared is not None else None


@dataclass
class Visible:
    doc: Document
    access: str  # OWNER | FAMILY
    link: FamilyLink | None = None


async def get_visible(db: AsyncSession, user: User, uid: str, *, ip: str | None = None) -> Visible:
    doc = await db.scalar(select(Document).where(Document.document_uid == uid[:60]))
    if doc is None or doc.deleted_yn:
        raise document_not_found()
    if doc.owner_user_no == user.user_no:
        return Visible(doc, "OWNER")
    link = await _family_link_for(db, user.user_no, doc)
    if link is not None:
        return Visible(doc, "FAMILY", link)
    audit(db, "ACCESS_DENIED", user.user_no, document=doc.document_no, target=doc.owner_user_no, success=False,
          reason="document", ip=ip)
    await db.commit()
    raise document_not_found()


async def _owned(db: AsyncSession, user: User, uid: str, *, ip: str | None) -> Document:
    v = await get_visible(db, user, uid, ip=ip)
    if v.access != "OWNER":
        audit(db, "ACCESS_DENIED", user.user_no, document=v.doc.document_no, target=v.doc.owner_user_no,
              success=False, reason="owner_only", ip=ip)
        await db.commit()
        raise FamilyError(403, "owner_only", "서류 주인만 바꿀 수 있어요.")
    return v.doc


async def visible_json(db: AsyncSession, v: Visible) -> dict:
    todos = (await todos_of(db, [v.doc.document_no]))[v.doc.document_no]
    owner_label = None
    if v.access == "FAMILY" and v.link is not None:
        owner_label = label_of_senior(v.link, await db.get(User, v.doc.owner_user_no))
    return document_json(v.doc, todos, access=v.access, owner_label=owner_label)


async def list_family_documents(db: AsyncSession, user: User) -> list[dict]:
    """연결된 가족의 서류. 주인 줄의 can_view_yn 이 켜져 있고, 내가 보냈거나 주인이 나눠 준 것만.
    부르는 이름(owner.label)은 내가 상대를 보는 줄의 별명이다."""
    grants = list(await db.scalars(select(UserFamily).where(
        UserFamily.family_user_no == user.user_no, UserFamily.deleted_yn.is_(False),
        UserFamily.is_active.is_(True), UserFamily.can_view_yn.is_(True))))
    out: list[dict] = []
    seen: set[str] = set()
    for grant in grants:
        owner = await db.get(User, grant.primary_user_no)
        if owner is None or not owner.is_active:
            continue
        if await active_link_between(db, user.user_no, owner.user_no) is None:
            continue
        shared_ids = select(DocumentShare.document_no).where(
            DocumentShare.shared_to_user_no == user.user_no, DocumentShare.revoked_yn.is_(False))
        docs = list(await db.scalars(select(Document).where(
            Document.owner_user_no == owner.user_no, Document.deleted_yn.is_(False),
            (Document.sender_user_no == user.user_no) | Document.document_no.in_(shared_ids))
            .order_by(Document.created_at.desc()).limit(MAX_LIST)))
        todos = await todos_of(db, [d.document_no for d in docs])
        mine = await family_mapping(db, user.user_no, owner.user_no)
        label = (mine.nickname if mine is not None and mine.nickname else None) or owner.name or "가족"
        for doc in docs:
            if doc.document_uid in seen:
                continue
            seen.add(doc.document_uid)
            out.append(document_json(doc, todos[doc.document_no], access="FAMILY", owner_label=label))
    out.sort(key=lambda j: j["createdAt"] or "", reverse=True)
    return out


# ---------- 바꾸기 (주인만) ----------

async def update_todo(db: AsyncSession, user: User, uid: str, todo_uid: str, *, done: bool | None,
                      remind: bool | None, ip: str | None) -> tuple[DocumentTodo, Document, bool]:
    """주인, 또는 주인 줄에서 can_edit_yn 을 받은 가족. 돌려주는 bool 은 '다른 사람에게 알릴지'."""
    v = await get_visible(db, user, uid, ip=ip)
    if v.access != "OWNER" and not await granted(db, v.doc.owner_user_no, user.user_no, "can_edit_yn"):
        audit(db, "ACCESS_DENIED", user.user_no, document=v.doc.document_no, target=v.doc.owner_user_no,
              success=False, reason="owner_only", ip=ip)
        await db.commit()
        raise FamilyError(403, "owner_only", "서류 주인만 바꿀 수 있어요.")
    doc = v.doc
    todo = await db.scalar(select(DocumentTodo).where(DocumentTodo.document_no == doc.document_no,
                                                      DocumentTodo.todo_uid == todo_uid[:40]))
    if todo is None:
        raise FamilyError(404, "todo_not_found", "할 일을 찾을 수 없어요.")
    now = utcnow()
    if done is not None and done != todo.done_yn:
        todo.done_yn = done
        todo.done_at, todo.done_by_user_no = (now, user.user_no) if done else (None, None)
    if remind is not None:
        todo.remind_yn = remind
    todo.updated_at = now
    doc.updated_at, doc.updated_by = now, user.user_no  # 다른 기기가 since 로 가져가게
    await db.commit()
    return todo, doc, user.user_no != doc.owner_user_no


async def mark_seen(db: AsyncSession, user: User, uid: str, *, ip: str | None) -> None:
    doc = await _owned(db, user, uid, ip=ip)
    if doc.owner_seen_at is None:
        now = utcnow()
        doc.owner_seen_at, doc.updated_at, doc.updated_by = now, now, user.user_no
        await db.commit()


async def delete_document(db: AsyncSession, user: User, uid: str, *, ip: str | None) -> None:
    """내용을 지우고 ID 만 남긴다. 주인, 보낸 사람, 또는 can_delete_yn 을 받은 가족."""
    v = await get_visible(db, user, uid, ip=ip)
    doc = v.doc
    allowed = (v.access == "OWNER" or doc.sender_user_no == user.user_no
               or await granted(db, doc.owner_user_no, user.user_no, "can_delete_yn"))
    if not allowed:
        audit(db, "ACCESS_DENIED", user.user_no, document=doc.document_no, target=doc.owner_user_no,
              success=False, reason="owner_only", ip=ip)
        await db.commit()
        raise FamilyError(403, "owner_only", "서류 주인만 바꿀 수 있어요.")
    now = utcnow()
    await db.execute(DocumentTodo.__table__.delete().where(DocumentTodo.document_no == doc.document_no))
    await db.execute(update(DocumentShare).where(DocumentShare.document_no == doc.document_no,
                                                 DocumentShare.revoked_yn.is_(False))
                     .values(revoked_yn=True, revoked_at=now))
    doc.deleted_yn, doc.deleted_at = True, now
    doc.title = doc.one_liner = doc.model_cd = doc.sender_label = None
    doc.amount, doc.due_date = None, None
    doc.warnings, doc.details = [], []
    doc.updated_at, doc.updated_by = now, user.user_no
    audit(db, "DOC_DELETE", user.user_no, document=doc.document_no, ip=ip)
    await db.commit()


# ---------- 나누기 (어르신 → 자녀) ----------

async def share(db: AsyncSession, user: User, uid: str, link_ids: list[int] | None, *,
                ip: str | None) -> tuple[Document, list[tuple[LinkView, bool]]]:
    """(서류, [(연결, 이번에 새로 나눴나)]). link_ids 가 없으면 내가 어르신인 모든 연결."""
    doc = await _owned(db, user, uid, ip=ip)
    views: list[LinkView] = []
    if link_ids is None:
        for link in await db.scalars(select(FamilyLink).where(FamilyLink.senior_user_no == user.user_no,
                                                              FamilyLink.status_cd == "ACTIVE")):
            try:
                views.append(await get_link_for(db, link.family_link_no, user.user_no))
            except FamilyError:
                continue
    else:
        for link_no in dict.fromkeys(link_ids):
            v = await get_link_for(db, link_no, user.user_no)
            if v.my_role != "SENIOR":
                raise FamilyError(403, "not_senior", "어르신 쪽에서만 자녀에게 보낼 수 있어요.")
            views.append(v)
    if not views:
        raise FamilyError(409, "no_family", "연결된 자녀가 없어요. 먼저 가족을 연결해 주세요.")
    now = utcnow()
    out = []
    for v in views:
        exists = await db.scalar(select(DocumentShare.share_no).where(
            DocumentShare.document_no == doc.document_no, DocumentShare.shared_to_user_no == v.other.user_no,
            DocumentShare.revoked_yn.is_(False)).limit(1))
        if exists is None:
            db.add(DocumentShare(document_no=doc.document_no, family_link_no=v.link.family_link_no,
                                 shared_by_user_no=user.user_no, shared_to_user_no=v.other.user_no, created_at=now))
            audit(db, "DOC_SHARE", user.user_no, link=v.link.family_link_no, document=doc.document_no,
                  target=v.other.user_no, ip=ip)
        out.append((v, exists is None))
    await db.commit()
    return doc, out


async def unshare(db: AsyncSession, user: User, uid: str, link_no: int, *, ip: str | None) -> None:
    doc = await _owned(db, user, uid, ip=ip)
    now = utcnow()
    res = await db.execute(update(DocumentShare).where(
        DocumentShare.document_no == doc.document_no, DocumentShare.family_link_no == link_no,
        DocumentShare.revoked_yn.is_(False)).values(revoked_yn=True, revoked_at=now))
    if res.rowcount:
        audit(db, "DOC_UNSHARE", user.user_no, link=link_no, document=doc.document_no, ip=ip)
    await db.commit()


# ---------- 대신 보내기 (자녀 → 어르신) ----------

async def check_can_send(db: AsyncSession, fs: FamilySettings, user: User, link_no: int) -> LinkView:
    """AI 를 부르기 전에 확인한다 (권한 없는 요청에 돈을 쓰지 않게)."""
    v = await get_link_for(db, link_no, user.user_no)
    if not await granted(db, v.other.user_no, user.user_no, "can_edit_yn"):
        if v.my_role != "CHILD":
            raise FamilyError(403, "not_child", "자녀로 연결된 가족만 대신 보낼 수 있어요.")
        raise FamilyError(403, "cannot_edit", "이 가족 서류는 대신 보낼 권한이 없어요.")
    since = utcnow() - timedelta(days=1)
    n = await db.scalar(select(func.count()).select_from(Document).where(
        Document.sender_user_no == user.user_no, Document.owner_user_no == v.other.user_no,
        Document.source_cd == "FAMILY", Document.created_at > since))
    if (n or 0) >= fs.send_daily_limit:
        raise FamilyError(429, "send_limit", "오늘은 더 보낼 수 없어요. 내일 다시 보내 주세요.")
    return v


async def store_sent(db: AsyncSession, user: User, link_no: int, result: AnalysisResult, *,
                     page_count: int, ip: str | None) -> tuple[Document, LinkView]:
    """AI 가 끝난 뒤 연결을 다시 확인하고(그 사이 끊겼을 수 있다) 어르신 서류로 보관."""
    v = await get_link_for(db, link_no, user.user_no)
    if not await granted(db, v.other.user_no, user.user_no, "can_edit_yn"):
        if v.my_role != "CHILD":
            raise FamilyError(403, "not_child", "자녀로 연결된 가족만 대신 보낼 수 있어요.")
        raise FamilyError(403, "cannot_edit", "이 가족 서류는 대신 보낼 권한이 없어요.")
    owner_row = await family_mapping(db, v.other.user_no, user.user_no)
    sender_label = (owner_row.nickname if owner_row and owner_row.nickname else None) or label_of_child(v.link, user)
    doc = await _create(db, result.model_dump(), uid=new_uid(), owner=v.other.user_no, sender=user.user_no,
                        source="FAMILY", link_no=link_no, sender_label=sender_label,
                        page_count=page_count)
    audit(db, "DOC_SEND", user.user_no, link=link_no, document=doc.document_no, target=v.other.user_no, ip=ip)
    await db.commit()
    return doc, v
