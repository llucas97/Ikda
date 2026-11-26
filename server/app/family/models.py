"""가족 연결·서류·푸시 기록 표. db/migrations/V0002__ct_family_document.sql 과 같은 모양이어야 한다."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.models import FALSE, PK
from ..db import Base, UTCDateTime, utcnow

JSONList = JSON().with_variant(JSONB(), "postgresql")


class FamilyLink(Base):
    __tablename__ = "ct_family_link"
    __table_args__ = (
        CheckConstraint("senior_user_no <> child_user_no", name="ck_ct_family_link_not_self"),
        Index("ux_ct_family_link_pair_active", "senior_user_no", "child_user_no", unique=True,
              postgresql_where=text("status_cd = 'ACTIVE'"), sqlite_where=text("status_cd = 'ACTIVE'")),
        Index("ix_ct_family_link_child", "child_user_no", "status_cd"),
    )

    family_link_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    senior_user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    child_user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    senior_label: Mapped[str | None] = mapped_column(String(30))
    child_label: Mapped[str | None] = mapped_column(String(30))
    status_cd: Mapped[str] = mapped_column(String(20), default="ACTIVE", server_default="ACTIVE")
    invite_no: Mapped[int | None] = mapped_column(BigInteger)
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime)
    unlinked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    unlinked_by_user_no: Mapped[int | None] = mapped_column(BigInteger)
    unlink_reason_cd: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class FamilyInvite(Base):
    __tablename__ = "ct_family_invite"
    __table_args__ = (
        Index("ux_ct_family_invite_code_pending", "code_hash", unique=True,
              postgresql_where=text("status_cd = 'PENDING'"), sqlite_where=text("status_cd = 'PENDING'")),
        Index("ux_ct_family_invite_token", "link_token_hash", unique=True),
        Index("ix_ct_family_invite_inviter", "inviter_user_no", "status_cd"),
    )

    invite_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    inviter_user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    inviter_role_cd: Mapped[str] = mapped_column(String(20))
    invitee_label: Mapped[str | None] = mapped_column(String(30))
    code_hash: Mapped[str] = mapped_column(String(64))
    link_token_hash: Mapped[str] = mapped_column(String(64))
    status_cd: Mapped[str] = mapped_column(String(20), default="PENDING", server_default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    accepted_user_no: Mapped[int | None] = mapped_column(BigInteger)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    family_link_no: Mapped[int | None] = mapped_column(BigInteger)
    relation_cd: Mapped[str | None] = mapped_column(String(20))
    counter_relation_cd: Mapped[str | None] = mapped_column(String(20))
    counter_nickname: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class UserFamily(Base):
    """대표 회원이 가족을 보는 한 줄. 연결마다 반대 방향 줄이 하나 더 있다."""

    __tablename__ = "ct_user_family"
    __table_args__ = (
        CheckConstraint("primary_user_no <> family_user_no", name="ck_ct_user_family_not_self"),
        Index("ux_ct_user_family_pair_alive", "primary_user_no", "family_user_no", unique=True,
              postgresql_where=text("deleted_yn = false"), sqlite_where=text("deleted_yn = 0")),
        Index("ix_ct_user_family_member", "family_user_no", "deleted_yn"),
    )

    family_mapping_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    primary_user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    family_user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    relation_cd: Mapped[str] = mapped_column(String(20))
    nickname: Mapped[str | None] = mapped_column(String(50))
    is_primary_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    can_view_yn: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    can_edit_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    can_delete_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    notification_yn: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    memo: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    deleted_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deleted_by: Mapped[int | None] = mapped_column(BigInteger)


class Document(Base):
    __tablename__ = "ct_document"
    __table_args__ = (
        Index("ux_ct_document_uid", "document_uid", unique=True),
        Index("ix_ct_document_owner", "owner_user_no", "updated_at"),
        Index("ix_ct_document_sender", "sender_user_no", "created_at"),
    )

    document_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    document_uid: Mapped[str] = mapped_column(String(40))
    owner_user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    sender_user_no: Mapped[int | None] = mapped_column(BigInteger)
    family_link_no: Mapped[int | None] = mapped_column(BigInteger)
    sender_label: Mapped[str | None] = mapped_column(String(30))
    source_cd: Mapped[str] = mapped_column(String(20), default="SELF", server_default="SELF")
    doc_type_cd: Mapped[str] = mapped_column(String(20), default="other", server_default="other")
    title: Mapped[str | None] = mapped_column(String(200))
    one_liner: Mapped[str | None] = mapped_column(String(1000))
    amount: Mapped[int | None] = mapped_column(BigInteger)
    due_date: Mapped[date | None] = mapped_column(Date)
    warnings: Mapped[list] = mapped_column(JSONList, default=list)
    details: Mapped[list] = mapped_column(JSONList, default=list)
    model_cd: Mapped[str | None] = mapped_column(String(100))
    page_count: Mapped[int | None] = mapped_column(Integer)
    owner_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    deleted_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class DocumentTodo(Base):
    __tablename__ = "ct_document_todo"
    __table_args__ = (Index("ux_ct_document_todo_uid", "document_no", "todo_uid", unique=True),)

    todo_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    document_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_document.document_no"))
    todo_uid: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    detail: Mapped[str | None] = mapped_column(String(500))
    done_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    remind_yn: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    done_by_user_no: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class DocumentShare(Base):
    __tablename__ = "ct_document_share"
    __table_args__ = (
        Index("ux_ct_document_share_active", "document_no", "shared_to_user_no", unique=True,
              postgresql_where=text("revoked_yn = false"), sqlite_where=text("revoked_yn = 0")),
        Index("ix_ct_document_share_to", "shared_to_user_no", "revoked_yn"),
    )

    share_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    document_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_document.document_no"))
    family_link_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_family_link.family_link_no"))
    shared_by_user_no: Mapped[int] = mapped_column(BigInteger)
    shared_to_user_no: Mapped[int] = mapped_column(BigInteger)
    revoked_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PushLog(Base):
    __tablename__ = "ct_push_log"
    __table_args__ = (Index("ix_ct_push_log_user", "user_no", "created_at"),)

    push_log_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_no: Mapped[int] = mapped_column(BigInteger)
    push_token_no: Mapped[int | None] = mapped_column(BigInteger)
    event_cd: Mapped[str] = mapped_column(String(30))
    document_no: Mapped[int | None] = mapped_column(BigInteger)
    family_link_no: Mapped[int | None] = mapped_column(BigInteger)
    sender_cd: Mapped[str] = mapped_column(String(20))
    result_cd: Mapped[str] = mapped_column(String(20))
    message_id: Mapped[str | None] = mapped_column(String(200))
    error_cd: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class FamilyLog(Base):
    __tablename__ = "ct_family_log"
    __table_args__ = (
        Index("ix_ct_family_log_actor", "actor_user_no", "event_cd", "created_at"),
        Index("ix_ct_family_log_ip", "ip_address", "event_cd", "created_at"),
    )

    family_log_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    actor_user_no: Mapped[int | None] = mapped_column(BigInteger)
    event_cd: Mapped[str] = mapped_column(String(30))
    family_link_no: Mapped[int | None] = mapped_column(BigInteger)
    invite_no: Mapped[int | None] = mapped_column(BigInteger)
    document_no: Mapped[int | None] = mapped_column(BigInteger)
    target_user_no: Mapped[int | None] = mapped_column(BigInteger)
    success_yn: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    fail_reason: Mapped[str | None] = mapped_column(String(200))
    ip_address: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
