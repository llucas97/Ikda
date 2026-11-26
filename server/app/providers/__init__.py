"""AI_PROVIDER=fake|gemini|anthropic (비우면 키가 있는 것 자동 선택, 없으면 fake)."""
from __future__ import annotations

import os

from .base import ImageInput, Provider, ProviderError  # noqa: F401
from .fake import FakeProvider


def get_provider() -> Provider:
    choice = os.getenv("AI_PROVIDER", "").strip().lower()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    if choice == "fake":
        return FakeProvider()
    if choice == "gemini" or (not choice and gemini_key):
        if not gemini_key:
            raise RuntimeError("AI_PROVIDER=gemini 인데 GEMINI_API_KEY 가 없어요")
        from .gemini import GeminiProvider
        return GeminiProvider(gemini_key)
    if choice == "anthropic" or (not choice and anthropic_key):
        if not anthropic_key:
            raise RuntimeError("AI_PROVIDER=anthropic 인데 ANTHROPIC_API_KEY 가 없어요")
        from .anthropic import AnthropicProvider
        return AnthropicProvider(anthropic_key)
    return FakeProvider()
