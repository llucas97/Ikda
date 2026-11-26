"""Anthropic Claude (Messages API). 정확도가 더 필요할 때 쓰는 공급자.

구조화 출력은 '도구 하나를 강제로 부르게' 해서 JSON 스키마를 지키게 한다.
지시문(system)에 cache_control 을 걸어 반복 호출 비용을 줄인다.
"""
from __future__ import annotations

import base64
import os

import httpx

from ..schema import CLASSIFY_JSON_SCHEMA, EXTRACT_JSON_SCHEMA
from ..prompt import CLASSIFY_PROMPT, SYSTEM_PROMPT, user_prompt
from .base import ImageInput, ProviderError

API = "https://api.anthropic.com/v1/messages"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.classify_model = os.getenv("ANTHROPIC_CLASSIFY_MODEL", "claude-haiku-5-5")
        self.default_model = os.getenv("ANTHROPIC_DEFAULT_MODEL", "claude-haiku-5-5")
        self.strong_model = os.getenv("ANTHROPIC_STRONG_MODEL", "claude-sonnet-5-5")
        self.fallback_models = [m for m in os.getenv("ANTHROPIC_FALLBACK_MODELS", "").split(",") if m]
        self._client = client

    async def _call(self, model: str, system: str, text: str, images: list[ImageInput],
                    tool_name: str, schema: dict, max_tokens: int) -> dict:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": i.mime_type,
                                         "data": base64.b64encode(i.data).decode()}}
            for i in images
        ]
        content.append({"type": "text", "text": text})
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": [{"name": tool_name, "description": "서류 분석 결과를 보고한다", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": tool_name},
            "messages": [{"role": "user", "content": content}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        client = self._client or httpx.AsyncClient(timeout=90)
        try:
            r = await client.post(API, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise ProviderError(f"anthropic {model} network: {type(e).__name__} {e}") from e
        finally:
            if self._client is None:
                await client.aclose()
        if r.status_code != 200:
            raise ProviderError(f"anthropic {model} {r.status_code}: {r.text[:600]}", status=r.status_code)
        from ..usage import record
        um = r.json().get("usage") or {}
        record(model, um.get("input_tokens", 0) + um.get("cache_read_input_tokens", 0)
               + um.get("cache_creation_input_tokens", 0), um.get("output_tokens", 0),
               um.get("cache_read_input_tokens", 0))
        try:
            for block in r.json()["content"]:
                if block.get("type") == "tool_use" and block.get("name") == tool_name:
                    return block["input"]
        except (KeyError, ValueError) as e:
            raise ProviderError(f"anthropic bad response: {e}") from e
        raise ProviderError("anthropic: no tool_use block")

    async def classify(self, images: list[ImageInput], model: str) -> str:
        out = await self._call(model, CLASSIFY_PROMPT, "종류를 골라.", images, "report_type", CLASSIFY_JSON_SCHEMA, 200)
        return str(out.get("docType", "other"))

    async def extract(self, images: list[ImageInput], model: str, doc_type_hint: str | None) -> dict:
        from .. import clock
        return await self._call(model, SYSTEM_PROMPT, user_prompt(clock.today(), doc_type_hint), images,
                                "report_document", EXTRACT_JSON_SCHEMA, 2000)
