"""요청 하나 동안 AI 호출별 토큰 수를 모은다 (비용 추적용, 내용은 남기지 않음)."""
from __future__ import annotations

from contextvars import ContextVar

_calls: ContextVar[list[dict] | None] = ContextVar("usage_calls", default=None)


def start() -> list[dict]:
    calls: list[dict] = []
    _calls.set(calls)
    return calls


def record(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> None:
    calls = _calls.get()
    if calls is not None:
        calls.append({"model": model, "inputTokens": input_tokens,
                      "outputTokens": output_tokens, "cachedTokens": cached_tokens})
