"""회원의 살아 있는 기기마다 푸시를 보내고 ct_push_log 에 남긴다. 푸시 실패가 본 요청을 실패시키지 않는다."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.models import UserPushToken
from ..db import utcnow
from ..family.models import PushLog
from .base import PushMessage, PushResult, PushSender

log = logging.getLogger("ilgeodeurim.push")


async def notify_user(db: AsyncSession, sender: PushSender | None, user_no: int, event: str, message: PushMessage,
                      *, document_no: int | None = None, family_link_no: int | None = None,
                      timeout_s: float = 8.0) -> int:
    """보낸(성공한) 기기 수. 본 트랜잭션을 commit 한 뒤에 부른다(여기서도 commit 한다)."""
    now = utcnow()

    def row(result: str, *, token_no: int | None = None, r: PushResult | None = None) -> PushLog:
        return PushLog(user_no=user_no, push_token_no=token_no, event_cd=event, document_no=document_no,
                       family_link_no=family_link_no, sender_cd=sender.code if sender else "NONE",
                       result_cd=result, message_id=r.message_id if r else None,
                       error_cd=(r.error if r else None), created_at=now)

    if sender is None:
        db.add(row("DISABLED"))
        await db.commit()
        return 0
    tokens = list(await db.scalars(select(UserPushToken)
                                   .where(UserPushToken.user_no == user_no, UserPushToken.active_yn.is_(True))
                                   .order_by(UserPushToken.updated_at.desc()).limit(10)))
    if not tokens:
        db.add(row("NO_TOKEN"))
        await db.commit()
        return 0

    sent = 0
    for t in tokens:
        try:
            r = await asyncio.wait_for(sender.send(t.push_token, message), timeout=timeout_s)
        except asyncio.TimeoutError:
            r = PushResult(False, error="TIMEOUT")
        except Exception as e:  # 발송 수단의 예상 못 한 오류도 본 요청을 깨뜨리지 않는다
            log.exception("push sender crashed")
            r = PushResult(False, error=type(e).__name__[:100])
        if r.ok:
            sent += 1
            db.add(row("SENT", token_no=t.push_token_no, r=r))
        elif r.invalid_token:
            db.add(row("INVALID_TOKEN", token_no=t.push_token_no, r=r))
            await db.execute(update(UserPushToken).where(UserPushToken.push_token_no == t.push_token_no)
                             .values(active_yn=False, updated_at=now))
        else:
            db.add(row("FAILED", token_no=t.push_token_no, r=r))
    await db.commit()
    return sent
