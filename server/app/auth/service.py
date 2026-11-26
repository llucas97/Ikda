"""회원 가입·로그인·세션 회전·로그아웃·탈퇴. 함수 하나가 트랜잭션 하나다(끝에서 commit).

세션 = ct_user_access 의 token_family 하나. refresh 를 쓸 때마다 새 행을 만들고 이전 행에 used_at 을 찍는다.
이미 쓴 refresh 가 다시 오면(유예 시간 밖) 탈취로 보고 그 세션 전체를 끊는다 (OAuth 2.0 Security BCP 4.14).
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from . import pkce, redirect
from .config import AuthSettings
from .errors import MSG_LOGIN_AGAIN, MSG_LOGIN_FAILED, AuthError, ProviderAuthError
from .models import OAuthAuthorize, User, UserAccess, UserLoginLog, UserOAuth, UserPushToken
from .providers import Provider, ProviderProfile
from .tokens import AccessClaims, decode_access_token, issue_access_token, new_id, new_refresh_token, sha256_hex
from ..db import utcnow

log = logging.getLogger("ilgeodeurim.auth")

USER_TYPES = ("SENIOR", "CHILD")
MSG_INACTIVE = "지금은 쓸 수 없는 계정이에요."
MAX_REFRESH_LEN = 200


@dataclass(frozen=True)
class ClientMeta:
    ip: str | None = None
    user_agent: str | None = None
    device_id: str | None = None
    device_os: str | None = None
    client_type: str = "APP"


@dataclass
class IssuedTokens:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    sid: str
    user: User
    providers: list[str]
    is_new_user: bool = False


def _log(db: AsyncSession, event: str, meta: ClientMeta, *, user_no: int | None = None,
         provider: str | None = None, success: bool = True, reason: str | None = None) -> None:
    db.add(UserLoginLog(
        user_no=user_no, event_cd=event, oauth_provider_cd=provider, client_type_cd=meta.client_type,
        device_id=meta.device_id, ip_address=meta.ip, user_agent=(meta.user_agent or "")[:500] or None,
        success_yn=success, fail_reason=reason[:200] if reason else None,
    ))


async def log_failure(db: AsyncSession, event: str, meta: ClientMeta, *, provider: str | None,
                      reason: str, user_no: int | None = None) -> None:
    """실패 이력은 따로 commit 한다 (본 트랜잭션은 되돌려도 남아야 한다)."""
    await db.rollback()
    _log(db, event, meta, user_no=user_no, provider=provider, success=False, reason=reason)
    await db.commit()


async def providers_of(db: AsyncSession, user_no: int) -> list[str]:
    rows = await db.scalars(select(UserOAuth.oauth_provider_cd)
                            .where(UserOAuth.user_no == user_no, UserOAuth.deleted_yn.is_(False))
                            .order_by(UserOAuth.oauth_no))
    return list(rows)


# ---------- 가입·연결 ----------

async def _find_link(db: AsyncSession, provider: str, oauth_id: str) -> UserOAuth | None:
    return await db.scalar(select(UserOAuth).where(
        UserOAuth.oauth_provider_cd == provider, UserOAuth.oauth_id == oauth_id, UserOAuth.deleted_yn.is_(False)))


async def upsert_user(db: AsyncSession, profile: ProviderProfile, *, user_type: str | None,
                      now: datetime, _retry: bool = True) -> tuple[User, bool]:
    """제공자 ID 로 회원을 찾고, 없으면 만든다. 이메일로 다른 회원에 붙이지 않는다."""
    link = await _find_link(db, profile.provider, profile.oauth_id)
    if link is not None:
        user = await db.get(User, link.user_no)
        if user is None or not user.is_active:
            raise AuthError(403, "user_inactive", MSG_INACTIVE)
        link.oauth_email = profile.email
        link.oauth_email_verified_yn = profile.email_verified
        link.oauth_name = profile.name
        link.oauth_picture = profile.picture
        link.last_login_at = now
        if not user.name and profile.name:
            user.name = profile.name[:50]
        if not user.profile_image_url and profile.picture:
            user.profile_image_url = profile.picture[:500]
        if not user.email and profile.email and profile.email_verified:
            user.email = profile.email[:100]
        return user, False

    user = User(
        user_type_cd=user_type if user_type in USER_TYPES else "SENIOR",
        user_grade_cd="MEMBER",
        email=profile.email[:100] if profile.email and profile.email_verified else None,
        name=(profile.name or "")[:50] or None,
        profile_image_url=(profile.picture or "")[:500] or None,
        status_cd="ACTIVE",
        join_channel_cd=profile.provider,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    try:
        await db.flush()
        user.created_by = user.updated_by = user.user_no
        db.add(UserOAuth(
            user_no=user.user_no, oauth_provider_cd=profile.provider, oauth_id=profile.oauth_id,
            oauth_email=profile.email, oauth_email_verified_yn=profile.email_verified,
            oauth_name=profile.name, oauth_picture=profile.picture, linked_at=now, last_login_at=now,
            created_at=now, updated_at=now,
        ))
        await db.flush()
    except IntegrityError:
        # 같은 계정으로 동시에 처음 로그인했다. 먼저 만든 쪽을 쓴다.
        await db.rollback()
        if not _retry:
            raise AuthError(409, "conflict", MSG_LOGIN_FAILED) from None
        return await upsert_user(db, profile, user_type=user_type, now=now, _retry=False)
    return user, True


# ---------- 세션 ----------

async def _issue(db: AsyncSession, s: AuthSettings, user: User, *, family: str, parent: int | None,
                 auth_at: datetime, provider: str | None, meta: ClientMeta, now: datetime) -> IssuedTokens:
    refresh = new_refresh_token()
    jti = new_id()
    refresh_exp = min(now + timedelta(seconds=s.refresh_ttl_s), auth_at + timedelta(seconds=s.session_max_s))
    access, access_exp = issue_access_token(s, user_no=user.user_no, user_type=user.user_type_cd,
                                            sid=family, jti=jti, now=now)
    db.add(UserAccess(
        user_no=user.user_no, client_type_cd=meta.client_type, token_family=family, parent_access_no=parent,
        access_jti=jti, refresh_token_hash=sha256_hex(refresh), login_provider_cd=provider,
        device_id=meta.device_id, device_os=meta.device_os, user_agent=(meta.user_agent or "")[:500] or None,
        ip_address=meta.ip, auth_at=auth_at, expires_at=access_exp, refresh_expires_at=refresh_exp,
        created_at=now,
    ))
    user.last_login_at = now
    user.last_login_client_cd = meta.client_type
    if provider:
        user.last_login_provider_cd = provider
    return IssuedTokens(access, access_exp, refresh, refresh_exp, family, user, await providers_of(db, user.user_no))


async def revoke_family(db: AsyncSession, family: str, reason: str, now: datetime) -> None:
    await db.execute(update(UserAccess)
                     .where(UserAccess.token_family == family, UserAccess.revoked_yn.is_(False))
                     .values(revoked_yn=True, revoked_at=now, revoke_reason_cd=reason))


async def revoke_all(db: AsyncSession, user_no: int, reason: str, now: datetime) -> None:
    await db.execute(update(UserAccess)
                     .where(UserAccess.user_no == user_no, UserAccess.revoked_yn.is_(False))
                     .values(revoked_yn=True, revoked_at=now, revoke_reason_cd=reason))


async def _enforce_session_limit(db: AsyncSession, s: AuthSettings, user_no: int, now: datetime) -> None:
    if s.max_sessions_per_user <= 0:
        return
    rows = await db.execute(
        select(UserAccess.token_family, func.max(UserAccess.created_at).label("last"))
        .where(UserAccess.user_no == user_no, UserAccess.revoked_yn.is_(False),
               UserAccess.refresh_expires_at > now)
        .group_by(UserAccess.token_family)
        .order_by(func.max(UserAccess.created_at).desc(), UserAccess.token_family)
    )
    for family, _ in list(rows)[s.max_sessions_per_user:]:
        await revoke_family(db, family, "SESSION_LIMIT", now)


async def start_session(db: AsyncSession, s: AuthSettings, user: User, *, provider: str, meta: ClientMeta,
                        now: datetime) -> IssuedTokens:
    tokens = await _issue(db, s, user, family=new_id(), parent=None, auth_at=now, provider=provider,
                          meta=meta, now=now)
    await db.flush()
    await _enforce_session_limit(db, s, user.user_no, now)
    return tokens


async def login_with_profile(db: AsyncSession, s: AuthSettings, profile: ProviderProfile, *,
                             user_type: str | None, meta: ClientMeta) -> IssuedTokens:
    """모바일 흐름: 앱 SDK 토큰을 제공자에게 확인한 뒤 부른다."""
    now = utcnow()
    user, is_new = await upsert_user(db, profile, user_type=user_type, now=now)
    if is_new:
        _log(db, "SIGNUP", meta, user_no=user.user_no, provider=profile.provider)
    tokens = await start_session(db, s, user, provider=profile.provider, meta=meta, now=now)
    tokens.is_new_user = is_new
    _log(db, "LOGIN", meta, user_no=user.user_no, provider=profile.provider)
    await db.commit()
    return tokens


async def rotate_refresh(db: AsyncSession, s: AuthSettings, refresh_token: str | None,
                         meta: ClientMeta) -> IssuedTokens:
    now = utcnow()
    if not refresh_token or len(refresh_token) > MAX_REFRESH_LEN:
        raise AuthError(401, "invalid_refresh", MSG_LOGIN_AGAIN)
    row = await db.scalar(select(UserAccess)
                          .where(UserAccess.refresh_token_hash == sha256_hex(refresh_token))
                          .with_for_update())
    if row is None:
        raise AuthError(401, "invalid_refresh", MSG_LOGIN_AGAIN)
    if row.revoked_yn:
        raise AuthError(401, "refresh_revoked", MSG_LOGIN_AGAIN)
    if row.used_at is not None:
        if now - row.used_at <= timedelta(seconds=s.refresh_reuse_grace_s):
            # 앱이 같은 토큰으로 거의 동시에 두 번 갱신했다. 먼저 성공한 쪽 토큰을 쓰면 된다.
            raise AuthError(401, "refresh_superseded", MSG_LOGIN_AGAIN)
        await revoke_family(db, row.token_family, "REUSE_DETECTED", now)
        _log(db, "REUSE_DETECTED", meta, user_no=row.user_no, provider=row.login_provider_cd,
             success=False, reason="refresh_reused")
        await db.commit()
        log.warning("refresh token reuse detected user=%s family=%s", row.user_no, row.token_family[:8])
        raise AuthError(401, "refresh_reused", MSG_LOGIN_AGAIN)
    if row.refresh_expires_at <= now or row.auth_at + timedelta(seconds=s.session_max_s) <= now:
        raise AuthError(401, "refresh_expired", MSG_LOGIN_AGAIN)

    user = await db.get(User, row.user_no)
    if user is None or not user.is_active:
        await revoke_family(db, row.token_family, "USER_INACTIVE", now)
        await db.commit()
        raise AuthError(401, "user_inactive", MSG_INACTIVE)

    # 같은 행을 두 요청이 동시에 잡아도 한쪽만 이긴다 (SQLite 처럼 FOR UPDATE 가 없어도).
    claimed = await db.execute(update(UserAccess)
                               .where(UserAccess.access_no == row.access_no, UserAccess.used_at.is_(None),
                                      UserAccess.revoked_yn.is_(False))
                               .values(used_at=now))
    if claimed.rowcount != 1:
        await db.rollback()
        raise AuthError(401, "refresh_superseded", MSG_LOGIN_AGAIN)

    meta = replace(meta, device_id=meta.device_id or row.device_id, device_os=meta.device_os or row.device_os,
                   client_type=row.client_type_cd or meta.client_type)
    tokens = await _issue(db, s, user, family=row.token_family, parent=row.access_no, auth_at=row.auth_at,
                          provider=row.login_provider_cd, meta=meta, now=now)
    await db.commit()
    return tokens


async def authenticate(db: AsyncSession, s: AuthSettings, token: str) -> tuple[User, AccessClaims]:
    """Bearer access token → 회원. 로그아웃·탈퇴·재사용 탐지로 끊긴 세션의 토큰은 만료 전이라도 거절한다."""
    claims = decode_access_token(s, token)
    user = await db.get(User, claims.user_no)
    if user is None or not user.is_active:
        raise AuthError(401, "user_inactive", MSG_LOGIN_AGAIN)
    alive = await db.scalar(select(UserAccess.access_no)
                            .where(UserAccess.token_family == claims.sid, UserAccess.user_no == claims.user_no,
                                   UserAccess.revoked_yn.is_(False))
                            .limit(1))
    if alive is None:
        raise AuthError(401, "session_revoked", MSG_LOGIN_AGAIN)
    return user, claims


async def logout(db: AsyncSession, *, refresh_token: str | None, claims: AccessClaims | None,
                 all_devices: bool, meta: ClientMeta) -> None:
    """언제나 성공처럼 끝난다(모르는 토큰이어도). 다른 회원의 세션은 끊지 않는다."""
    now = utcnow()
    user_no: int | None = claims.user_no if claims else None
    if all_devices:
        if claims is None:
            raise AuthError(401, "login_required", MSG_LOGIN_AGAIN)
        await revoke_all(db, claims.user_no, "LOGOUT_ALL", now)
        await db.execute(update(UserPushToken).where(UserPushToken.user_no == claims.user_no)
                         .values(active_yn=False, updated_at=now))
        _log(db, "LOGOUT_ALL", meta, user_no=claims.user_no)
        await db.commit()
        return

    family: str | None = None
    if refresh_token and len(refresh_token) <= MAX_REFRESH_LEN:
        row = await db.scalar(select(UserAccess).where(UserAccess.refresh_token_hash == sha256_hex(refresh_token)))
        if row is not None and (claims is None or claims.user_no == row.user_no):
            family, user_no = row.token_family, row.user_no
    if family is None and claims is not None:
        family = claims.sid
    if family is None:
        return
    await revoke_family(db, family, "LOGOUT", now)
    if user_no is not None and meta.device_id:
        await db.execute(update(UserPushToken)
                         .where(UserPushToken.user_no == user_no, UserPushToken.device_id == meta.device_id)
                         .values(active_yn=False, updated_at=now))
    _log(db, "LOGOUT", meta, user_no=user_no)
    await db.commit()


async def register_push_token(db: AsyncSession, user_no: int, *, push_token: str, platform: str,
                              device_id: str | None) -> None:
    """같은 (회원, 토큰) 이면 갱신하고, 그 토큰을 가진 다른 회원은 끈다.

    AsOne insertOrUpdatePushToken + deactivateOtherDevicesWithSameToken.
    PostgreSQL · SQLite 모두 (user_no, push_token) 유니크에 ON CONFLICT.
    """
    now = utcnow()
    token = push_token[:500]
    platform_cd = platform.upper()[:20]
    device = (device_id or "")[:100] or None
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    stmt = insert(UserPushToken).values(
        user_no=user_no, push_token=token, platform_cd=platform_cd, device_id=device,
        active_yn=True, created_at=now, updated_at=now,
    ).on_conflict_do_update(
        index_elements=["user_no", "push_token"],
        set_={"platform_cd": platform_cd, "device_id": device, "active_yn": True, "updated_at": now},
    )
    await db.execute(stmt)
    await db.execute(update(UserPushToken)
                     .where(UserPushToken.push_token == token, UserPushToken.user_no != user_no)
                     .values(active_yn=False, updated_at=now))
    await db.commit()


async def withdraw(db: AsyncSession, providers, user: User, *, kakao_access_token: str | None,
                   meta: ClientMeta) -> dict[str, str]:
    """탈퇴: 제공자 연결 끊기(되는 만큼) → 모든 세션·푸시 끊기 → 개인정보 지우고 논리삭제.

    제공자 연결 끊기가 실패해도 탈퇴는 끝까지 한다(결과는 unlink_result_cd 에 남긴다).
    """
    now = utcnow()
    links = list(await db.scalars(select(UserOAuth)
                                  .where(UserOAuth.user_no == user.user_no, UserOAuth.deleted_yn.is_(False))))
    results: dict[str, str] = {}
    for link in links:
        result = "SKIPPED"
        try:
            client = providers.get(link.oauth_provider_cd)
            token = kakao_access_token if link.oauth_provider_cd == "KAKAO" else None
            if link.oauth_id:
                result = await client.unlink(link.oauth_id, user_access_token=token)
        except AuthError:
            result = "SKIPPED"
        except Exception:  # 제공자 문제로 탈퇴가 막히면 안 된다
            log.exception("unlink failed provider=%s", link.oauth_provider_cd)
            result = "FAILED"
        results[link.oauth_provider_cd] = result
        link.unlink_result_cd = result
        link.unlinked_at = now
        link.deleted_yn = True
        link.oauth_id = None
        link.oauth_email = link.oauth_name = link.oauth_picture = None
        link.oauth_email_verified_yn = False
        link.updated_at = now

    await revoke_all(db, user.user_no, "WITHDRAW", now)
    await db.execute(update(UserPushToken).where(UserPushToken.user_no == user.user_no)
                     .values(active_yn=False, updated_at=now))
    user.status_cd = "WITHDRAW"
    user.status_reason = None
    user.status_changed_at = now
    user.withdraw_at = now
    user.withdraw_type_cd = "SELF"
    user.deleted_yn = True
    user.email = user.name = user.mobile_phone = user.gender_cd = user.profile_image_url = None
    user.birth_date = None
    user.updated_by = user.user_no
    user.updated_at = now
    _log(db, "WITHDRAW", meta, user_no=user.user_no)
    await db.commit()
    return results


# ---------- 서버 인가 코드 흐름 (state + PKCE) ----------

async def begin_authorize(db: AsyncSession, s: AuthSettings, provider: Provider, *, provider_name: str,
                          app_redirect_uri: str, app_state: str | None, app_code_challenge: str | None,
                          app_code_challenge_method: str | None, user_type: str | None,
                          device_id: str | None, login_hint: str | None) -> str:
    """제공자 로그인 주소를 만든다. redirect_uri 는 라우터가 먼저 허용 목록으로 확인한다."""
    if app_code_challenge_method != "S256" or not pkce.valid_challenge(app_code_challenge):
        raise AuthError(400, "invalid_code_challenge", MSG_LOGIN_FAILED)
    if app_state is not None and len(app_state) > 200:
        raise AuthError(400, "invalid_state", MSG_LOGIN_FAILED)
    now = utcnow()
    state = secrets.token_urlsafe(32)
    verifier = pkce.new_verifier()
    nonce = secrets.token_urlsafe(24)
    url = provider.authorize_url(state=state, code_challenge=pkce.s256(verifier), nonce=nonce,
                                 login_hint=login_hint)
    db.add(OAuthAuthorize(
        oauth_provider_cd=provider.code, state_hash=sha256_hex(state), provider_code_verifier=verifier,
        nonce=nonce, app_redirect_uri=app_redirect_uri, app_state=app_state,
        app_code_challenge=app_code_challenge, user_type_cd=user_type if user_type in USER_TYPES else None,
        device_id=(device_id or "")[:100] or None, expires_at=now + timedelta(seconds=s.authorize_ttl_s),
        created_at=now,
    ))
    await db.commit()
    return url


async def complete_callback(db: AsyncSession, s: AuthSettings, provider: Provider, *, provider_name: str,
                            state: str | None, code: str | None, error: str | None, meta: ClientMeta) -> str:
    """제공자 콜백. 언제나 앱으로 돌아갈 주소를 돌려준다(성공이면 1회용 로그인 코드)."""
    now = utcnow()
    fail_base = redirect.default_callback(s)

    def failed(base: str, reason: str, app_state: str | None, message: str = MSG_LOGIN_FAILED) -> str:
        return redirect.login_failed_url(base, provider=provider_name, reason=reason, message=message,
                                         app_state=app_state)

    if not state or len(state) > 200:
        return failed(fail_base, "invalid_state", None)
    row = await db.scalar(select(OAuthAuthorize).where(OAuthAuthorize.state_hash == sha256_hex(state)))
    if row is None or row.oauth_provider_cd != provider.code:
        return failed(fail_base, "invalid_state", None)
    claimed = await db.execute(update(OAuthAuthorize)
                               .where(OAuthAuthorize.authorize_no == row.authorize_no,
                                      OAuthAuthorize.callback_at.is_(None), OAuthAuthorize.expires_at > now)
                               .values(callback_at=now))
    await db.commit()  # state 는 성공·실패와 상관없이 한 번 쓰면 끝
    if claimed.rowcount != 1:
        return failed(row.app_redirect_uri, "invalid_state", row.app_state)
    if error:
        reason = "cancelled" if error == "access_denied" else "provider_error"
        return failed(row.app_redirect_uri, reason, row.app_state,
                      "로그인을 취소했어요." if reason == "cancelled" else MSG_LOGIN_FAILED)
    if not code:
        return failed(row.app_redirect_uri, "provider_error", row.app_state)

    try:
        profile = await provider.exchange_code(code, code_verifier=row.provider_code_verifier, nonce=row.nonce)
        user, is_new = await upsert_user(db, profile, user_type=row.user_type_cd, now=now)
    except AuthError as e:
        await log_failure(db, "LOGIN_FAIL", replace(meta, device_id=row.device_id), provider=provider.code,
                          reason=e.code)
        return failed(row.app_redirect_uri, e.code if isinstance(e, ProviderAuthError) else "login_failed",
                      row.app_state, e.user_message)

    if is_new:
        _log(db, "SIGNUP", replace(meta, device_id=row.device_id), user_no=user.user_no, provider=profile.provider)
    login_code = secrets.token_urlsafe(32)
    row = await db.get(OAuthAuthorize, row.authorize_no)
    row.user_no = user.user_no
    row.is_new_user_yn = is_new
    row.login_code_hash = sha256_hex(login_code)
    row.login_code_expires_at = now + timedelta(seconds=s.login_code_ttl_s)
    await db.commit()
    return redirect.success_url(row.app_redirect_uri, login_code, row.app_state)


async def exchange_login_code(db: AsyncSession, s: AuthSettings, *, code: str | None, code_verifier: str | None,
                              redirect_uri: str | None, meta: ClientMeta) -> IssuedTokens:
    """앱이 딥링크로 받은 1회용 코드 + PKCE verifier → 우리 토큰."""
    now = utcnow()
    bad = AuthError(400, "invalid_grant", MSG_LOGIN_FAILED)
    if not code or len(code) > 200:
        raise bad
    row = await db.scalar(select(OAuthAuthorize).where(OAuthAuthorize.login_code_hash == sha256_hex(code)))
    if row is None:
        raise bad
    if row.consumed_at is not None:
        # 코드가 두 번 쓰였다 — 새어 나갔을 수 있으니 그 코드로 낸 세션도 끊는다 (RFC 6749 4.1.2).
        if row.issued_token_family:
            await revoke_family(db, row.issued_token_family, "CODE_REPLAY", now)
            await db.commit()
        raise bad
    claimed = await db.execute(update(OAuthAuthorize)
                               .where(OAuthAuthorize.authorize_no == row.authorize_no,
                                      OAuthAuthorize.consumed_at.is_(None))
                               .values(consumed_at=now))
    await db.commit()  # 검사에 실패해도 코드는 태운다 (verifier 를 여러 번 맞춰 보지 못하게)
    if claimed.rowcount != 1:
        raise bad
    if (row.login_code_expires_at is None or row.login_code_expires_at <= now
            or redirect_uri != row.app_redirect_uri
            or not pkce.verify(code_verifier, row.app_code_challenge)
            or row.user_no is None):
        raise bad

    user = await db.get(User, row.user_no)
    if user is None or not user.is_active:
        raise AuthError(403, "user_inactive", MSG_INACTIVE)
    meta = replace(meta, device_id=meta.device_id or row.device_id)
    tokens = await start_session(db, s, user, provider=row.oauth_provider_cd, meta=meta, now=now)
    tokens.is_new_user = row.is_new_user_yn
    fresh = await db.get(OAuthAuthorize, row.authorize_no)
    fresh.issued_token_family = tokens.sid
    _log(db, "LOGIN", meta, user_no=user.user_no, provider=row.oauth_provider_cd)
    await db.commit()
    return tokens
