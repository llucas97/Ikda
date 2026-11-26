"""모델 라우팅: 싼 모델로 종류를 먼저 고르고, 약·계약서는 더 좋은 모델로 올린다.

모델이 한도 초과(429)·권한 없음(403)·없음(404)·과부하(5xx)·시간 초과면 다음 모델로 넘어간다.
"""
from __future__ import annotations

import logging
import os

from .providers import ImageInput, Provider, ProviderError

log = logging.getLogger("ilgeodeurim")

ESCALATE = set(filter(None, os.getenv("ESCALATE_TYPES", "medicine,contract").split(",")))
RETRYABLE = {None, 403, 404, 408, 429, 500, 502, 503, 504}


def choose_model(provider: Provider, doc_type: str) -> str:
    return provider.strong_model if doc_type in ESCALATE or doc_type == "unknown" else provider.default_model


def model_chain(provider: Provider, doc_type: str) -> list[str]:
    chain = [choose_model(provider, doc_type), provider.default_model, *getattr(provider, "fallback_models", [])]
    return list(dict.fromkeys(chain))  # 순서 유지, 중복 제거


async def run(provider: Provider, images: list[ImageInput]) -> tuple[dict, str, str]:
    """(결과 dict, 분류된 종류, 실제로 쓴 모델)"""
    try:
        doc_type = await provider.classify(images, provider.classify_model)
    except ProviderError as e:
        # 종류를 모르면 약·계약서일 수도 있으니 안전하게 좋은 모델부터 시도
        log.warning("classify failed, use strong model: %s", str(e)[:200].replace("\n", " "))
        doc_type = "unknown"

    last: ProviderError | None = None
    for model in model_chain(provider, doc_type):
        try:
            raw = await provider.extract(images, model, doc_type if doc_type not in ("other", "unknown") else None)
            if doc_type == "unknown":
                doc_type = str(raw.get("docType", "other"))
            return raw, doc_type, model
        except ProviderError as e:
            if e.status not in RETRYABLE:
                raise
            log.warning("model %s failed (%s), trying next", model, e.status)
            last = e
    assert last is not None
    raise last
