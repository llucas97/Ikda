from __future__ import annotations

from .base import PushMessage, PushResult


class FakePushSender:
    """테스트·개발용. 보낸 것을 sent 에 쌓는다. 실제로는 아무 데도 보내지 않는다."""

    code = "FAKE"

    def __init__(self) -> None:
        self.sent: list[tuple[str, PushMessage]] = []
        self.invalid_tokens: set[str] = set()
        self.failing_tokens: set[str] = set()

    async def send(self, token: str, message: PushMessage) -> PushResult:
        if token in self.invalid_tokens:
            return PushResult(False, error="UNREGISTERED", invalid_token=True)
        if token in self.failing_tokens:
            return PushResult(False, error="UNAVAILABLE")
        self.sent.append((token, message))
        return PushResult(True, message_id=f"fake/{len(self.sent)}")

    def to(self, token: str) -> list[PushMessage]:
        return [m for t, m in self.sent if t == token]
