from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)  # FCM data 는 문자열만


@dataclass(frozen=True)
class PushResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None
    invalid_token: bool = False  # 토큰이 죽었다(앱 삭제 등). 다시 보내지 않게 끈다


class PushSender(Protocol):
    code: str  # ct_push_log.sender_cd (FCM / FAKE)

    async def send(self, token: str, message: PushMessage) -> PushResult: ...
