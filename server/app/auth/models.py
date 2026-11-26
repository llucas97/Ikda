"""회원·소셜 연결·세션 표. db/migrations/V0001__ct_member.sql 과 같은 모양이어야 한다."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, UTCDateTime, utcnow

# SQLite 는 INTEGER PRIMARY KEY 여야 자동증가한다. PostgreSQL 은 BIGSERIAL.
PK = BigInteger().with_variant(Integer, "sqlite")
FALSE = text("false")


class User(Base):
    __tablename__ = "ct_user"

    user_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_type_cd: Mapped[str] = mapped_column(String(20), default="SENIOR", server_default="SENIOR")
    user_grade_cd: Mapped[str] = mapped_column(String(20), default="MEMBER", server_default="MEMBER")
    email: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(50))
    mobile_phone: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)
    gender_cd: Mapped[str | None] = mapped_column(String(10))
    profile_image_url: Mapped[str | None] = mapped_column(String(500))
    status_cd: Mapped[str] = mapped_column(String(20), default="ACTIVE", server_default="ACTIVE")
    status_reason: Mapped[str | None] = mapped_column(String(500))
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    suspend_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    withdraw_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    withdraw_type_cd: Mapped[str | None] = mapped_column(String(20))
    join_channel_cd: Mapped[str | None] = mapped_column(String(30))
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_provider_cd: Mapped[str | None] = mapped_column(String(20))
    last_login_client_cd: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    deleted_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)

    @property
    def is_active(self) -> bool:
        return self.status_cd == "ACTIVE" and not self.deleted_yn


class UserOAuth(Base):
    __tablename__ = "ct_user_oauth"
    __table_args__ = (
        Index("ux_ct_user_oauth_provider_id", "oauth_provider_cd", "oauth_id", unique=True,
              postgresql_where=text("deleted_yn = false"), sqlite_where=text("deleted_yn = 0")),
        Index("ux_ct_user_oauth_user_provider", "user_no", "oauth_provider_cd", unique=True,
              postgresql_where=text("deleted_yn = false"), sqlite_where=text("deleted_yn = 0")),
    )

    oauth_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    oauth_provider_cd: Mapped[str] = mapped_column(String(20))
    oauth_id: Mapped[str | None] = mapped_column(String(100))
    oauth_email: Mapped[str | None] = mapped_column(String(100))
    oauth_email_verified_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    oauth_name: Mapped[str | None] = mapped_column(String(100))
    oauth_picture: Mapped[str | None] = mapped_column(String(500))
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    unlinked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    unlink_result_cd: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    deleted_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)


class UserAccess(Base):
    __tablename__ = "ct_user_access"
    __table_args__ = (
        Index("ux_ct_user_access_refresh_hash", "refresh_token_hash", unique=True),
        Index("ix_ct_user_access_family", "token_family"),
        Index("ix_ct_user_access_user", "user_no", "created_at"),
    )

    access_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    client_type_cd: Mapped[str] = mapped_column(String(20), default="APP", server_default="APP")
    token_family: Mapped[str] = mapped_column(String(64))
    parent_access_no: Mapped[int | None] = mapped_column(BigInteger)
    access_jti: Mapped[str] = mapped_column(String(64))
    refresh_token_hash: Mapped[str] = mapped_column(String(64))
    login_provider_cd: Mapped[str | None] = mapped_column(String(20))
    device_id: Mapped[str | None] = mapped_column(String(100))
    device_os: Mapped[str | None] = mapped_column(String(30))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(50))
    auth_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    refresh_expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoke_reason_cd: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UserLoginLog(Base):
    __tablename__ = "ct_user_login_log"
    __table_args__ = (Index("ix_ct_user_login_log_user", "user_no", "created_at"),)

    login_log_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_no: Mapped[int | None] = mapped_column(BigInteger)
    event_cd: Mapped[str] = mapped_column(String(30))
    oauth_provider_cd: Mapped[str | None] = mapped_column(String(20))
    client_type_cd: Mapped[str | None] = mapped_column(String(20))
    device_id: Mapped[str | None] = mapped_column(String(100))
    ip_address: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    success_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    fail_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UserPushToken(Base):
    __tablename__ = "ct_user_push_token"
    __table_args__ = (Index("ux_ct_user_push_token_user_token", "user_no", "push_token", unique=True),)

    push_token_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_no: Mapped[int] = mapped_column(BigInteger, ForeignKey("ct_user.user_no"))
    push_token: Mapped[str] = mapped_column(String(500))
    platform_cd: Mapped[str | None] = mapped_column(String(20))
    device_id: Mapped[str | None] = mapped_column(String(100))
    active_yn: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class OAuthAuthorize(Base):
    __tablename__ = "ct_oauth_authorize"
    __table_args__ = (
        Index("ux_ct_oauth_authorize_state", "state_hash", unique=True),
        Index("ux_ct_oauth_authorize_login_code", "login_code_hash", unique=True),
    )

    authorize_no: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    oauth_provider_cd: Mapped[str] = mapped_column(String(20))
    state_hash: Mapped[str] = mapped_column(String(64))
    provider_code_verifier: Mapped[str] = mapped_column(String(128))
    nonce: Mapped[str | None] = mapped_column(String(64))
    app_redirect_uri: Mapped[str] = mapped_column(String(500))
    app_state: Mapped[str | None] = mapped_column(String(200))
    app_code_challenge: Mapped[str] = mapped_column(String(128))
    user_type_cd: Mapped[str | None] = mapped_column(String(20))
    device_id: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    callback_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    user_no: Mapped[int | None] = mapped_column(BigInteger)
    is_new_user_yn: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    login_code_hash: Mapped[str | None] = mapped_column(String(64))
    login_code_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    issued_token_family: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
