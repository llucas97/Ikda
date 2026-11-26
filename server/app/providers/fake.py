"""API 키 없이 앱↔서버 전체 흐름을 시험하기 위한 가짜 공급자.

사진 파일 이름에 bill/전기/고지, med/약, hosp/병원 등이 있으면 그 종류로,
없으면 사진 내용 해시로 세 종류 중 하나를 고른다(같은 사진 → 같은 결과).
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from .base import ImageInput

_HINTS = {
    "bill": ("bill", "전기", "고지", "요금", "elec"),
    "medicine": ("med", "약", "pill", "drug"),
    "hospital": ("hosp", "병원", "검진", "clinic"),
    "contract": ("contract", "계약"),
    "government": ("gov", "주민센터", "구청", "공단"),
}
_CYCLE = ("bill", "medicine", "hospital")


def _pick_type(images: list[ImageInput]) -> str:
    names = " ".join(i.filename.lower() for i in images)
    for t, keys in _HINTS.items():
        if any(k in names for k in keys):
            return t
    h = hashlib.sha256(b"".join(i.data[:4096] for i in images)).digest()
    return _CYCLE[h[0] % len(_CYCLE)]


def _d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _md(n: int) -> str:
    d = date.today() + timedelta(days=n)
    return f"{d.month}월 {d.day}일"


def fake_result(doc_type: str) -> dict:
    if doc_type == "bill":
        return {
            "readable": True, "docType": "bill", "title": "한국전력 전기요금 고지서",
            "oneLiner": f"이번 달 전기요금 32,400원을 {_md(9)}까지 내시면 돼요. 자동이체가 아니라서 직접 내셔야 해요.",
            "amount": 32400, "dueDate": _d(9),
            "todos": [
                {"title": "전기요금 내기", "dueDate": _d(9), "detail": "은행, 편의점, 한전ON 앱에서 낼 수 있어요"},
                {"title": "자동이체 신청 생각해 보기", "dueDate": None, "detail": "한 번 신청하면 매달 알아서 빠져나가요"},
            ],
            "warnings": ["기한이 지나면 연체료가 붙어요."],
            "details": ["청구 금액: 32,400원", "사용 기간: 지난달 1일 ~ 말일", "사용량: 285kWh", "고객번호: 끝자리 4521"],
        }
    if doc_type == "medicine":
        return {
            "readable": True, "docType": "medicine", "title": "약봉투 (혈압약 외 2종)",
            "oneLiner": "하루 세 번, 식사하고 30분 뒤에 한 봉지씩 드세요. 7일 치예요.",
            "amount": None, "dueDate": _d(7),
            "todos": [
                {"title": "약 다 드신 뒤 다시 진료", "dueDate": _d(7), "detail": "7일 치라서 다 드시면 병원에 다시 가세요"},
            ],
            "warnings": ["정확한 복용법은 약봉투와 약사 안내를 꼭 다시 확인해 주세요.", "술과 함께 드시지 마세요."],
            "details": ["복용: 하루 3회, 식후 30분", "기간: 7일분", "약국: 행복약국"],
        }
    if doc_type == "hospital":
        return {
            "readable": True, "docType": "hospital", "title": "건강검진 예약 안내",
            "oneLiner": f"{_md(8)} 아침 8시 30분에 건강검진이 있어요. 전날 밤 9시부터 아무것도 드시면 안 돼요.",
            "amount": None, "dueDate": _d(8),
            "todos": [
                {"title": "전날 밤 9시부터 음식 안 먹기", "dueDate": _d(7), "detail": "물도 가급적 드시지 마세요"},
                {"title": "건강검진 가기", "dueDate": _d(8), "detail": "아침 8시 30분, 신분증 꼭 챙기기"},
            ],
            "warnings": ["혈압약은 아침에 물 조금과 드셔도 되는지 병원에 먼저 물어보세요."],
            "details": ["장소: 서울중앙병원 본관 2층", "시간: 오전 8시 30분", "준비물: 신분증, 문진표"],
        }
    return {
        "readable": True, "docType": doc_type, "title": "서류",
        "oneLiner": "서류 내용을 정리했어요. 자세한 내용을 확인해 주세요.",
        "amount": None, "dueDate": None, "todos": [],
        "warnings": ["도장 찍기 전에 가족이나 전문가와 꼭 같이 확인하세요."] if doc_type == "contract" else [],
        "details": [],
    }


class FakeProvider:
    name = "fake"
    classify_model = "fake-classify"
    default_model = "fake-default"
    strong_model = "fake-strong"
    fallback_models: list[str] = []

    async def classify(self, images: list[ImageInput], model: str) -> str:
        return _pick_type(images)

    async def extract(self, images: list[ImageInput], model: str, doc_type_hint: str | None) -> dict:
        return fake_result(doc_type_hint or _pick_type(images))
