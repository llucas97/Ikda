"""앱과 서버가 주고받는 JSON 계약 (Flutter: lib/services/analysis_service.dart 와 같은 모양)."""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DocType = Literal["bill", "medicine", "hospital", "contract", "government", "other"]
DOC_TYPES: tuple[str, ...] = ("bill", "medicine", "hospital", "contract", "government", "other")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clean_date(v: str | None) -> str | None:
    if v in (None, "", "null"):
        return None
    v = str(v).strip()
    if not _DATE_RE.match(v):
        return None
    try:
        date.fromisoformat(v)
    except ValueError:
        return None
    return v


class Todo(BaseModel):
    id: str = Field(default_factory=lambda: f"t_{uuid.uuid4().hex[:8]}")
    title: str
    dueDate: str | None = None  # YYYY-MM-DD
    detail: str | None = None

    @field_validator("dueDate", mode="before")
    @classmethod
    def _v_date(cls, v):
        return _clean_date(v)


class AnalysisResult(BaseModel):
    id: str = Field(default_factory=lambda: f"doc_{uuid.uuid4().hex[:12]}")
    docType: DocType = "other"
    title: str
    oneLiner: str  # 쉬운 말 한두 문장
    amount: int | None = None  # 원 단위 정수 (예: 32400)
    dueDate: str | None = None  # 가장 중요한 기한 YYYY-MM-DD
    todos: list[Todo] = []
    warnings: list[str] = []
    details: list[str] = []
    model: str | None = None  # 어떤 모델이 만들었는지 (디버그·비용 추적용)

    @field_validator("dueDate", mode="before")
    @classmethod
    def _v_date(cls, v):
        return _clean_date(v)

    @field_validator("docType", mode="before")
    @classmethod
    def _v_type(cls, v):
        return v if v in DOC_TYPES else "other"

    @field_validator("amount", mode="before")
    @classmethod
    def _v_amount(cls, v):
        if v in (None, "", "null"):
            return None
        if isinstance(v, str):
            digits = re.sub(r"[^\d]", "", v)
            return int(digits) if digits else None
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
        return n if n >= 0 else None


class ApiError(BaseModel):
    code: str
    userMessage: str  # 어르신에게 그대로 보여줄 문장


# LLM 에게 주는 출력 스키마 (JSON Schema). readable=false 면 다시 찍기 안내.
EXTRACT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean", "description": "글씨를 읽을 수 있으면 true"},
        "docType": {"type": "string", "enum": list(DOC_TYPES)},
        "title": {"type": "string", "description": "서류 이름. 예: 한국전력 전기요금 고지서"},
        "oneLiner": {"type": "string", "description": "어르신께 드리는 쉬운 말 요약, 해요체 1~2문장"},
        "amount": {"type": ["integer", "null"], "description": "내야 할 돈(원, 정수). 없으면 null"},
        "dueDate": {"type": ["string", "null"], "description": "가장 중요한 기한 YYYY-MM-DD. 없으면 null"},
        "todos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "할 일, 짧게. 예: 전기요금 내기"},
                    "dueDate": {"type": ["string", "null"]},
                    "detail": {"type": ["string", "null"], "description": "방법·준비물 한 줄"},
                },
                "required": ["title", "dueDate", "detail"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
        "details": {"type": "array", "items": {"type": "string"}, "description": "'항목: 값' 형태 3~5줄"},
    },
    "required": ["readable", "docType", "title", "oneLiner", "amount", "dueDate", "todos", "warnings", "details"],
}

CLASSIFY_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {"docType": {"type": "string", "enum": list(DOC_TYPES)}},
    "required": ["docType"],
}
