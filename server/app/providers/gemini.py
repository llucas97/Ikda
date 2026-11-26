"""Google Gemini (REST generateContent). 값싸서 기본 공급자로 추천."""
from __future__ import annotations

import base64
import json
import os

import httpx

from ..schema import CLASSIFY_JSON_SCHEMA, EXTRACT_JSON_SCHEMA
from ..prompt import CLASSIFY_PROMPT, SYSTEM_PROMPT, user_prompt
from .base import ImageInput, ProviderError

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.classify_model = os.getenv("GEMINI_CLASSIFY_MODEL", "gemini-3.5-flash-lite")
        # 2026-11-16 실측: gemini-3.8-flash 는 이 키로 60~120초 무응답이라 기본값을 3.6-flash 로 둠
        self.default_model = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-3.6-flash")
        self.strong_model = os.getenv("GEMINI_STRONG_MODEL", "gemini-3.1-pro-preview")
        # 앞 모델이 한도 초과(429)·과부하(503)·시간 초과면 차례로 시도
        self.fallback_models = [m for m in os.getenv(
            "GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite").split(",") if m]
        self.thinking_level = os.getenv("GEMINI_THINKING_LEVEL", "low")  # minimal|low|medium|high
        self.timeout = float(os.getenv("GEMINI_TIMEOUT_S", "45"))
        self._client = client

    def _parts(self, images: list[ImageInput]) -> list[dict]:
        return [
            {"inline_data": {"mime_type": i.mime_type, "data": base64.b64encode(i.data).decode()}}
            for i in images
        ]

    async def _call(self, model: str, system: str, text: str, images: list[ImageInput], schema: dict) -> dict:
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [*self._parts(images), {"text": text}]}],
            # Gemini 3 는 temperature 기본값(1.0) 유지가 권장이라 따로 주지 않는다
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        if model.startswith("gemini-3") and self.thinking_level:
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": self.thinking_level}
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            r = await client.post(API.format(model=model), json=body, headers={"x-goog-api-key": self.api_key})
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini {model} network: {type(e).__name__} {e}") from e
        finally:
            if self._client is None:
                await client.aclose()
        if r.status_code != 200:
            raise ProviderError(f"gemini {model} {r.status_code}: {r.text[:600]}", status=r.status_code)
        from ..usage import record
        um = r.json().get("usageMetadata") or {}
        record(model, um.get("promptTokenCount", 0),
               um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0),
               um.get("cachedContentTokenCount", 0))
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            text_out = "".join(p.get("text", "") for p in parts)
            return json.loads(text_out)
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"gemini bad response: {e}") from e

    async def classify(self, images: list[ImageInput], model: str) -> str:
        out = await self._call(model, CLASSIFY_PROMPT, "종류만 JSON 으로 답해.", images, CLASSIFY_JSON_SCHEMA)
        return str(out.get("docType", "other"))

    async def extract(self, images: list[ImageInput], model: str, doc_type_hint: str | None) -> dict:
        from .. import clock
        return await self._call(model, SYSTEM_PROMPT, user_prompt(clock.today(), doc_type_hint), images, EXTRACT_JSON_SCHEMA)
