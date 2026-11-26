"""가족 연결: 초대(6자리 번호 + 링크) → 한 번 눌러 수락 → 연결 → 어느 쪽이든 끊기.

보안 규칙 (docs/phase3-plan.md §3):
- 번호는 HMAC-SHA256(JWT_SECRET) 만, 링크 토큰은 SHA-256 만 저장. 30분, 한 번만, 새로 만들면 이전 것은 취소.
- 번호 맞히기 막기: 회원별·IP별로 틀린 횟수를 세어 넘치면 429.
- 연결은 두 사람 사이에 하나. 역할(SENIOR/CHILD)은 연결이 정한다(ct_user.user_type_cd 는 화면 기본값일 뿐).
- 상대가 탈퇴·정지면 연결을 없는 것으로 본다.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.config import AuthSettings
from ..auth.models import User
from ..auth.tokens import sha256_hex
from ..db import utcnow
from .config import FamilySettings
from .errors import FamilyError, invite_invalid, link_not_found
from .models import Document, DocumentShare, DocumentTodo, FamilyInvite, FamilyLink, FamilyLog, UserFamily
from .relations import normalize_relation, resolve_relation

ROLES = ("SENIOR", "CHILD")
CODE_DIGITS = 6
MAX_TOKEN_LEN = 100
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


# ---------- 작은 도우미 ----------

def other_role(role: str) -> str:
    return "CHILD" if role == "SENIOR" else "SENIOR"


def code_hash(secret: str, code: str) -> str:
    # 6자리는 경우의 수가 100만뿐이라 그냥 해시면 바로 거꾸로 풀린다. 서버 비밀로 HMAC.
    return hmac.new(secret.encode(), f"family-invite:{code}".encode(), hashlib.sha256).hexdigest()


def normalize_code(raw: str | None) -> str | None:
    """'123 456', '123-456' 도 받는다. 숫자 6자리가 아니면 None."""
    if not raw:
        return None
    digits = re.sub(r"[\s-]", "", unicodedata.normalize("NFKC", raw))
    return digits if len(digits) == CODE_DIGITS and digits.isdigit() else None


def clean_label(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = "".join(ch for ch in unicodedata.normalize("NFC", raw) if unicodedata.category(ch)[0] != "C").strip()
    return s[:30] or None


def has_batchim(word: str) -> bool:
    if not word:
        return False
    c = ord(word[-1])
    if 0xAC00 <= c <= 0xD7A3:
        return (c - 0xAC00) % 28 != 0
    return word[-1].isdigit() and word[-1] in "013678"


def josa(word: str, with_batchim: str, without: str) -> str:
    return word + (with_batchim if has_batchim(word) else without)


def label_of_senior(link: FamilyLink, senior: User | None) -> str:
    """자녀 화면에서 어르신을 부르는 이름."""
    return link.senior_label or (senior.name if senior and senior.name else None) or "부모님"


def label_of_child(link: FamilyLink, child: User | None) -> str:
    """어르신 화면에서 자녀를 부르는 이름."""
    return link.child_label or (child.name if child and child.name else None) or "자녀"


def audit(db: AsyncSession, event: str, actor: int | None, *, link: int | None = None, invite: int | None = None,
          document: int | None = None, target: int | None = None, success: bool = True,
          reason: str | None = None, ip: str | None = None) -> None:
    db.add(FamilyLog(actor_user_no=actor, event_cd=event, family_link_no=link, invite_no=invite,
                     document_no=document, target_user_no=target, success_yn=success,
                     fail_reason=reason[:200] if reason else None, ip_address=ip, created_at=utcnow()))


async def _active_user(db: AsyncSession, user_no: int) -> User | None:
    u = await db.get(User, user_no)
    return u if u is not None and u.is_active else None


# ---------- 연결 찾기 (권한의 바탕) ----------

@dataclass
class LinkView:
    link: FamilyLink
    my_role: str
    other: User
    relation_cd: str = "OTHER"
    nickname: str | None = None
    mapping_no: int | None = None
    is_primary: bool = False
    can_view: bool = True
    can_edit: bool = False
    can_delete: bool = False
    notification: bool = True
    can_send: bool = False

    @property
    def other_label(self) -> str:
        if self.nickname:
            return self.nickname
        return label_of_child(self.link, self.other) if self.my_role == "SENIOR" else label_of_senior(self.link, self.other)


async def get_link_for(db: AsyncSession, link_no: int, user_no: int, *, need_other_active: bool = True) -> LinkView:
    """내가 한쪽인 살아 있는 연결. 아니면 404 (남의 연결이 있는지도 알려 주지 않는다)."""
    link = await db.get(FamilyLink, link_no)
    if link is None or link.status_cd != "ACTIVE" or user_no not in (link.senior_user_no, link.child_user_no):
        raise link_not_found()
    my_role = "SENIOR" if link.senior_user_no == user_no else "CHILD"
    other_no = link.child_user_no if my_role == "SENIOR" else link.senior_user_no
    other = await db.get(User, other_no)
    if other is None or (need_other_active and not other.is_active):
        raise link_not_found()
    return await _with_mapping(db, LinkView(link, my_role, other), user_no)


async def active_link_between(db: AsyncSession, a: int, b: int) -> FamilyLink | None:
    return await db.scalar(select(FamilyLink).where(
        FamilyLink.status_cd == "ACTIVE",
        or_((FamilyLink.senior_user_no == a) & (FamilyLink.child_user_no == b),
            (FamilyLink.senior_user_no == b) & (FamilyLink.child_user_no == a))).limit(1))


async def senior_child_link(db: AsyncSession, senior_no: int, child_no: int) -> FamilyLink | None:
    """정확히 이 방향(어르신·자녀)의 살아 있는 연결. 둘 다 활성 회원이어야 한다."""
    link = await db.scalar(select(FamilyLink).where(
        FamilyLink.status_cd == "ACTIVE", FamilyLink.senior_user_no == senior_no,
        FamilyLink.child_user_no == child_no).limit(1))
    if link is None:
        return None
    if await _active_user(db, senior_no) is None or await _active_user(db, child_no) is None:
        return None
    return link


# ---------- 초대 ----------

@dataclass
class NewInvite:
    invite: FamilyInvite
    code: str
    token: str


def require_relation(raw: str | None) -> str | None:
    code = normalize_relation(raw)
    if code == "":
        raise FamilyError(400, "bad_relation", "관계를 다시 골라 주세요.")
    return code


async def create_invite(db: AsyncSession, s: AuthSettings, fs: FamilySettings, user: User, *, role: str | None,
                        label: str | None, ip: str | None, relation: str | None = None,
                        counter_relation: str | None = None, counter_nickname: str | None = None) -> NewInvite:
    now = utcnow()
    uid = user.user_no  # rollback 뒤에는 ORM 객체를 건드리지 않는다 (비동기 지연 로딩 오류)
    my_role = role if role in ROLES else (user.user_type_cd if user.user_type_cd in ROLES else "SENIOR")
    relation_cd = require_relation(relation)
    counter_cd = require_relation(counter_relation)
    counter_name = clean_label(counter_nickname)
    for _ in range(8):
        # 어르신이 헷갈리지 않게 살아 있는 초대는 하나만. 새로 만들면 이전 것은 취소.
        await db.execute(update(FamilyInvite)
                         .where(FamilyInvite.inviter_user_no == uid, FamilyInvite.status_cd == "PENDING")
                         .values(status_cd="CANCELLED", updated_at=now))
        code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
        token = secrets.token_urlsafe(32)
        h = code_hash(s.jwt_secret, code)
        # 시간이 지났는데 아직 PENDING 인 같은 번호가 유일 인덱스를 막지 않게 먼저 만료 처리
        await db.execute(update(FamilyInvite)
                         .where(FamilyInvite.code_hash == h, FamilyInvite.status_cd == "PENDING",
                                FamilyInvite.expires_at <= now)
                         .values(status_cd="EXPIRED", updated_at=now))
        if await db.scalar(select(FamilyInvite.invite_no).where(
                FamilyInvite.code_hash == h, FamilyInvite.status_cd == "PENDING")) is not None:
            continue  # 지금 다른 사람이 쓰는 번호
        invite = FamilyInvite(inviter_user_no=uid, inviter_role_cd=my_role, invitee_label=clean_label(label),
                              relation_cd=relation_cd, counter_relation_cd=counter_cd, counter_nickname=counter_name,
                              code_hash=h, link_token_hash=sha256_hex(token), status_cd="PENDING",
                              expires_at=now + timedelta(seconds=fs.invite_ttl_s), created_at=now, updated_at=now)
        db.add(invite)
        try:
            await db.flush()
        except IntegrityError:  # 같은 순간 같은 번호. 다시 뽑는다
            await db.rollback()
            continue
        audit(db, "INVITE_CREATE", uid, invite=invite.invite_no, ip=ip)
        await db.commit()
        return NewInvite(invite, code, token)
    raise FamilyError(503, "invite_busy", "잠시 뒤에 다시 해 주세요.")


async def cancel_invite(db: AsyncSession, user: User, invite_no: int, *, ip: str | None) -> None:
    now = utcnow()
    res = await db.execute(update(FamilyInvite)
                           .where(FamilyInvite.invite_no == invite_no, FamilyInvite.inviter_user_no == user.user_no,
                                  FamilyInvite.status_cd == "PENDING")
                           .values(status_cd="CANCELLED", updated_at=now))
    if res.rowcount != 1:
        await db.rollback()
        raise invite_invalid()
    audit(db, "INVITE_CANCEL", user.user_no, invite=invite_no, ip=ip)
    await db.commit()


async def _guard_attempts(db: AsyncSession, fs: FamilySettings, user_no: int, ip: str | None, now: datetime) -> None:
    since = now - timedelta(seconds=fs.fail_window_s)
    by_user = await db.scalar(select(func.count()).select_from(FamilyLog).where(
        FamilyLog.actor_user_no == user_no, FamilyLog.event_cd == "INVITE_FAIL", FamilyLog.created_at > since))
    by_ip = 0
    if ip:
        by_ip = await db.scalar(select(func.count()).select_from(FamilyLog).where(
            FamilyLog.ip_address == ip, FamilyLog.event_cd == "INVITE_FAIL", FamilyLog.created_at > since))
    if (by_user or 0) >= fs.fail_limit_user or (by_ip or 0) >= fs.fail_limit_ip:
        minutes = max(1, fs.fail_window_s // 60)
        raise FamilyError(429, "too_many_attempts", f"너무 여러 번 틀렸어요. {minutes}분 뒤에 다시 해 주세요.")


async def _fail(db: AsyncSession, user_no: int, reason: str, ip: str | None, invite_no: int | None = None) -> FamilyError:
    audit(db, "INVITE_FAIL", user_no, invite=invite_no, success=False, reason=reason, ip=ip)
    await db.commit()
    return invite_invalid()


async def _find_pending(db: AsyncSession, s: AuthSettings, *, code: str | None, token: str | None,
                        now: datetime) -> FamilyInvite | None:
    if token:
        if len(token) > MAX_TOKEN_LEN or not _TOKEN_RE.match(token):
            return None
        cond = FamilyInvite.link_token_hash == sha256_hex(token)
    else:
        c = normalize_code(code)
        if c is None:
            return None
        cond = FamilyInvite.code_hash == code_hash(s.jwt_secret, c)
    return await db.scalar(select(FamilyInvite).where(cond, FamilyInvite.status_cd == "PENDING",
                                                      FamilyInvite.expires_at > now))


async def _usable_invite(db: AsyncSession, s: AuthSettings, fs: FamilySettings, user: User, *, code: str | None,
                         token: str | None, ip: str | None, now: datetime) -> tuple[FamilyInvite, User]:
    await _guard_attempts(db, fs, user.user_no, ip, now)
    invite = await _find_pending(db, s, code=code, token=token, now=now)
    if invite is None:
        raise await _fail(db, user.user_no, "not_found", ip)
    inviter = await _active_user(db, invite.inviter_user_no)
    if inviter is None:
        raise await _fail(db, user.user_no, "inviter_inactive", ip, invite.invite_no)
    if inviter.user_no == user.user_no:
        raise FamilyError(400, "invite_self", "내가 만든 번호예요. 가족에게 보내 주세요.")
    return invite, inviter


async def preview_invite(db: AsyncSession, s: AuthSettings, fs: FamilySettings, user: User, *, code: str | None,
                         token: str | None, ip: str | None) -> dict:
    """수락 전에 '누가 보낸 초대인지' 크게 보여 주려고."""
    now = utcnow()
    invite, inviter = await _usable_invite(db, s, fs, user, code=code, token=token, ip=ip, now=now)
    linked = await active_link_between(db, user.user_no, inviter.user_no) is not None
    return {
        "inviter": {"name": inviter.name, "profileImageUrl": inviter.profile_image_url},
        "inviterRole": invite.inviter_role_cd,
        "yourRole": other_role(invite.inviter_role_cd),
        "expiresAt": invite.expires_at,
        "alreadyLinked": linked,
        "relationCd": invite.relation_cd,
        "counterRelationCd": invite.counter_relation_cd,
        "counterNickname": invite.counter_nickname,
        "nickname": invite.invitee_label,
    }


async def accept_invite(db: AsyncSession, s: AuthSettings, fs: FamilySettings, user: User, *, code: str | None,
                        token: str | None, label: str | None, ip: str | None,
                        relation: str | None = None) -> tuple[LinkView, FamilyInvite]:
    now = utcnow()
    my_relation = require_relation(relation)
    invite, inviter = await _usable_invite(db, s, fs, user, code=code, token=token, ip=ip, now=now)
    uid, invite_no = user.user_no, invite.invite_no  # rollback 뒤에도 쓸 값
    if await active_link_between(db, uid, inviter.user_no) is not None:
        raise FamilyError(409, "already_linked", "이미 연결된 가족이에요.")
    senior, child = (inviter, user) if invite.inviter_role_cd == "SENIOR" else (user, inviter)
    n_children = await db.scalar(select(func.count()).select_from(FamilyLink).where(
        FamilyLink.senior_user_no == senior.user_no, FamilyLink.status_cd == "ACTIVE"))
    n_seniors = await db.scalar(select(func.count()).select_from(FamilyLink).where(
        FamilyLink.child_user_no == child.user_no, FamilyLink.status_cd == "ACTIVE"))
    if (n_children or 0) >= fs.max_children or (n_seniors or 0) >= fs.max_seniors:
        raise FamilyError(409, "family_limit", "더 연결할 수 없어요. 연결을 정리한 뒤 다시 해 주세요.")

    # 한 번만: 두 사람이 같은 번호를 동시에 눌러도 한 명만 이긴다.
    claimed = await db.execute(update(FamilyInvite)
                               .where(FamilyInvite.invite_no == invite.invite_no, FamilyInvite.status_cd == "PENDING",
                                      FamilyInvite.expires_at > now)
                               .values(status_cd="ACCEPTED", accepted_user_no=user.user_no, accepted_at=now,
                                       updated_at=now))
    if claimed.rowcount != 1:
        await db.rollback()
        raise await _fail(db, uid, "race_lost", ip, invite_no)

    # 초대한 사람이 붙인 이름은 받는 사람을 부르는 이름, 받는 사람이 붙인 이름은 초대한 사람을 부르는 이름.
    inviter_calls, acceptor_calls = invite.invitee_label, clean_label(label)
    senior_label, child_label = ((acceptor_calls, inviter_calls) if invite.inviter_role_cd == "SENIOR"
                                 else (inviter_calls, acceptor_calls))
    link = FamilyLink(senior_user_no=senior.user_no, child_user_no=child.user_no, senior_label=senior_label,
                      child_label=child_label, status_cd="ACTIVE", invite_no=invite.invite_no, linked_at=now,
                      created_at=now, created_by=user.user_no, updated_at=now, updated_by=user.user_no)
    db.add(link)
    # 초대한 사람이 보는 관계 / 수락한 사람이 보는 관계. 없으면 별명에서 짐작한다.
    inviter_rel = resolve_relation(invite.relation_cd, invite.invitee_label, other=my_relation)
    acceptor_rel = resolve_relation(my_relation, label, invite.counter_relation_cd, inviter_rel)
    if inviter_rel == "OTHER":
        inviter_rel = resolve_relation(None, invite.invitee_label, other=acceptor_rel)
    if invite.inviter_role_cd == "SENIOR":
        senior_rel, child_rel = inviter_rel, acceptor_rel
    else:
        senior_rel, child_rel = acceptor_rel, inviter_rel
    # 어르신 줄의 can_edit: 자녀가 대신 보낼 수 있게. 배우자끼리는 양쪽 다.
    spouse = senior_rel == "SPOUSE" and child_rel == "SPOUSE"
    _add_mapping(db, primary=senior.user_no, family=child.user_no, relation=senior_rel, nickname=child_label,
                 primary_member=True, can_edit=True, by=user.user_no, now=now)
    _add_mapping(db, primary=child.user_no, family=senior.user_no, relation=child_rel, nickname=senior_label,
                 primary_member=spouse, can_edit=spouse, by=user.user_no, now=now)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise FamilyError(409, "already_linked", "이미 연결된 가족이에요.") from None
    await db.execute(update(FamilyInvite).where(FamilyInvite.invite_no == invite.invite_no)
                     .values(family_link_no=link.family_link_no))
    audit(db, "INVITE_ACCEPT", user.user_no, link=link.family_link_no, invite=invite.invite_no,
          target=inviter.user_no, ip=ip)
    await db.commit()
    my_role = "SENIOR" if senior.user_no == user.user_no else "CHILD"
    return await _with_mapping(db, LinkView(link, my_role, inviter), user.user_no), invite


# ---------- 목록·이름·끊기 ----------

async def list_family(db: AsyncSession, user: User) -> tuple[list[LinkView], FamilyInvite | None]:
    links = list(await db.scalars(select(FamilyLink).where(
        FamilyLink.status_cd == "ACTIVE",
        or_(FamilyLink.senior_user_no == user.user_no, FamilyLink.child_user_no == user.user_no))
        .order_by(FamilyLink.linked_at)))
    views = []
    for link in links:
        my_role = "SENIOR" if link.senior_user_no == user.user_no else "CHILD"
        other = await _active_user(db, link.child_user_no if my_role == "SENIOR" else link.senior_user_no)
        if other is not None:
            views.append(await _with_mapping(db, LinkView(link, my_role, other), user.user_no))
    pending = await db.scalar(select(FamilyInvite).where(
        FamilyInvite.inviter_user_no == user.user_no, FamilyInvite.status_cd == "PENDING",
        FamilyInvite.expires_at > utcnow()).order_by(FamilyInvite.invite_no.desc()).limit(1))
    return views, pending


async def set_label(db: AsyncSession, user: User, link_no: int, label: str | None, *, ip: str | None,
                    relation: str | None = None, update_label: bool = True) -> LinkView:
    """내가 상대를 부르는 이름·관계만 바꾼다. 상대 줄은 건드리지 않는다."""
    view = await get_link_for(db, link_no, user.user_no)
    now = utcnow()
    cleaned = clean_label(label)
    if update_label:
        if view.my_role == "SENIOR":
            view.link.child_label = cleaned
        else:
            view.link.senior_label = cleaned
        view.link.updated_at, view.link.updated_by = now, user.user_no
    row = await family_mapping(db, user.user_no, view.other.user_no)
    if row is not None:
        if update_label:
            row.nickname = cleaned
            view.nickname = cleaned
        code = require_relation(relation)
        if code:
            row.relation_cd = code
            view.relation_cd = code
        row.updated_at, row.updated_by = now, user.user_no
    audit(db, "LINK_LABEL", user.user_no, link=link_no, target=view.other.user_no, ip=ip)
    await db.commit()
    return view


async def _close_link(db: AsyncSession, link: FamilyLink, by: int, reason: str, now: datetime) -> None:
    link.status_cd = "UNLINKED"
    link.unlinked_at, link.unlinked_by_user_no, link.unlink_reason_cd = now, by, reason
    link.updated_at, link.updated_by = now, by
    # 이 연결로 나눈 서류는 거둔다. 자녀가 보낸 서류는 어르신 것이라 그대로 둔다.
    await db.execute(update(DocumentShare)
                     .where(DocumentShare.family_link_no == link.family_link_no, DocumentShare.revoked_yn.is_(False))
                     .values(revoked_yn=True, revoked_at=now))
    # 양쪽 관계 줄을 함께 논리삭제. 다시 연결해도 예전 나눔은 살아나지 않는다.
    pair = or_(
        (UserFamily.primary_user_no == link.senior_user_no) & (UserFamily.family_user_no == link.child_user_no),
        (UserFamily.primary_user_no == link.child_user_no) & (UserFamily.family_user_no == link.senior_user_no),
    )
    await db.execute(update(UserFamily).where(pair, UserFamily.deleted_yn.is_(False)).values(
        deleted_yn=True, deleted_at=now, deleted_by=by, is_active=False, updated_at=now, updated_by=by))


async def unlink(db: AsyncSession, user: User, link_no: int, *, ip: str | None) -> None:
    """어느 쪽이든 끊을 수 있다. 상대가 정지 상태여도 끊을 수 있다."""
    view = await get_link_for(db, link_no, user.user_no, need_other_active=False)
    now = utcnow()
    await _close_link(db, view.link, user.user_no, "SELF", now)
    audit(db, "LINK_UNLINK", user.user_no, link=link_no, target=view.other.user_no, ip=ip)
    await db.commit()


async def on_user_withdrawn(db: AsyncSession, user_no: int) -> None:
    """탈퇴 뒤 정리: 연결 끊기, 초대 취소, 내 서류 지우기(사진은 원래 없음), 내가 보낸 서류의 내 이름 지우기."""
    now = utcnow()
    links = list(await db.scalars(select(FamilyLink).where(
        FamilyLink.status_cd == "ACTIVE",
        or_(FamilyLink.senior_user_no == user_no, FamilyLink.child_user_no == user_no))))
    for link in links:
        await _close_link(db, link, user_no, "WITHDRAW", now)
        audit(db, "LINK_UNLINK", user_no, link=link.family_link_no, reason="WITHDRAW")
    await db.execute(update(FamilyInvite)
                     .where(FamilyInvite.inviter_user_no == user_no, FamilyInvite.status_cd == "PENDING")
                     .values(status_cd="CANCELLED", updated_at=now))
    owned = select(Document.document_no).where(Document.owner_user_no == user_no)
    await db.execute(delete(DocumentShare).where(DocumentShare.document_no.in_(owned)))
    await db.execute(delete(DocumentTodo).where(DocumentTodo.document_no.in_(owned)))
    await db.execute(delete(Document).where(Document.owner_user_no == user_no))
    await db.execute(update(Document).where(Document.sender_user_no == user_no, Document.owner_user_no != user_no)
                     .values(sender_label=None))
    await db.commit()


# ---------- 관계 줄 (ct_user_family) ----------

def _add_mapping(db: AsyncSession, *, primary: int, family: int, relation: str, nickname: str | None,
                 primary_member: bool, can_edit: bool, by: int, now: datetime) -> None:
    db.add(UserFamily(
        primary_user_no=primary, family_user_no=family, relation_cd=relation or "OTHER",
        nickname=nickname, is_primary_yn=primary_member, is_active=True, can_view_yn=True,
        can_edit_yn=can_edit, can_delete_yn=False, notification_yn=True, created_at=now, created_by=by,
        updated_at=now, updated_by=by, deleted_yn=False,
    ))


async def family_mapping(db: AsyncSession, primary: int, family: int) -> UserFamily | None:
    return await db.scalar(select(UserFamily).where(
        UserFamily.primary_user_no == primary, UserFamily.family_user_no == family,
        UserFamily.deleted_yn.is_(False)).limit(1))


async def _with_mapping(db: AsyncSession, view: LinkView, user_no: int) -> LinkView:
    row = await family_mapping(db, user_no, view.other.user_no)
    if row is None:
        return view
    view.relation_cd = row.relation_cd
    view.nickname = row.nickname or view.other_label
    view.mapping_no = row.family_mapping_no
    view.is_primary = bool(row.is_primary_yn)
    view.can_view = bool(row.can_view_yn)
    view.can_edit = bool(row.can_edit_yn)
    view.can_delete = bool(row.can_delete_yn)
    view.notification = bool(row.notification_yn)
    theirs = await family_mapping(db, view.other.user_no, user_no)
    view.can_send = theirs is not None and bool(theirs.can_edit_yn) and bool(theirs.is_active)
    return view


async def granted(db: AsyncSession, owner_no: int, actor_no: int, flag: str) -> bool:
    """주인 줄에서 이 가족에게 준 권한. 보내기·고치기는 can_edit_yn, 알림은 받는 사람 줄의 notification_yn."""
    if actor_no == owner_no:
        return True
    row = await family_mapping(db, owner_no, actor_no)
    if row is None or not row.is_active:
        return False
    return bool(getattr(row, flag))


async def wants_push(db: AsyncSession, user_no: int, about_user_no: int) -> bool:
    row = await family_mapping(db, user_no, about_user_no)
    if row is None:
        return True
    return bool(row.notification_yn) and bool(row.is_active) and not row.deleted_yn


async def set_permissions(db: AsyncSession, user: User, link_no: int, *, can_view: bool | None,
                          can_edit: bool | None, can_delete: bool | None, notification: bool | None,
                          ip: str | None) -> LinkView:
    """대표(어르신)가 자기 줄의 권한을 고친다. 그 가족이 내 서류를 어떻게 다루는지."""
    view = await get_link_for(db, link_no, user.user_no)
    row = await family_mapping(db, user.user_no, view.other.user_no)
    if row is None or not row.is_primary_yn:
        raise FamilyError(403, "not_primary", "권한은 대표 가족만 바꿀 수 있어요.")
    now = utcnow()
    if can_view is not None:
        row.can_view_yn = can_view
    if can_edit is not None:
        row.can_edit_yn = can_edit
    if can_delete is not None:
        row.can_delete_yn = can_delete
    if notification is not None:
        row.notification_yn = notification
    row.updated_at, row.updated_by = now, user.user_no
    audit(db, "LINK_PERMISSION", user.user_no, link=link_no, target=view.other.user_no, ip=ip)
    await db.commit()
    return await _with_mapping(db, view, user.user_no)
