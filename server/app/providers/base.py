from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ImageInput:
    """요청 동안 메모리에만 있는 사진. 디스크에 쓰지 않는다."""
    data: bytes
    mime_type: str
    filename: str = ""


class ProviderError(Exception):
    """AI 공급자 호출 실패 (네트워크, 인증, 응답 형식 등). status: HTTP 상태(네트워크 오류면 None)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Provider(Protocol):
    name: str
    classify_model: str  # 싼 모델: 종류만 분류
    default_model: str   # 보통 서류 분석
    strong_model: str    # 약·계약서 등 정확도가 중요한 서류
    fallback_models: list[str]  # 위 모델이 막히면 차례로 시도

    async def classify(self, images: list[ImageInput], model: str) -> str: ...

    async def extract(self, images: list[ImageInput], model: str, doc_type_hint: str | None) -> dict: ...
