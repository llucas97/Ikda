"""가족 관계 코드. 각 줄은 '대표 회원(primary)이 상대를 보는 관계'다.

예: 어머니의 줄 relation_cd=DAUGHTER, nickname=큰딸.
    딸의 줄 relation_cd=MOTHER, nickname=어머니.
"""
from __future__ import annotations

RELATION_CODES = (
    "SPOUSE", "FATHER", "MOTHER", "SON", "DAUGHTER", "SON_IN_LAW", "DAUGHTER_IN_LAW",
    "GRANDCHILD", "BROTHER", "SISTER", "GRANDFATHER", "GRANDMOTHER", "OTHER",
)

RELATION_KO = {
    "SPOUSE": "배우자",
    "FATHER": "아버지",
    "MOTHER": "어머니",
    "SON": "아들",
    "DAUGHTER": "딸",
    "SON_IN_LAW": "사위",
    "DAUGHTER_IN_LAW": "며느리",
    "GRANDCHILD": "손주",
    "BROTHER": "형제",
    "SISTER": "자매",
    "GRANDFATHER": "할아버지",
    "GRANDMOTHER": "할머니",
    "OTHER": "가족",
}

# 상대가 관계를 안 골랐을 때의 기본 반대말. 수락 화면에서 바꿀 수 있다.
INVERSE = {
    "SPOUSE": "SPOUSE",
    "FATHER": "SON",
    "MOTHER": "DAUGHTER",
    "SON": "FATHER",
    "DAUGHTER": "MOTHER",
    "SON_IN_LAW": "FATHER",
    "DAUGHTER_IN_LAW": "MOTHER",
    "GRANDCHILD": "GRANDMOTHER",
    "BROTHER": "BROTHER",
    "SISTER": "SISTER",
    "GRANDFATHER": "GRANDCHILD",
    "GRANDMOTHER": "GRANDCHILD",
    "OTHER": "OTHER",
}

# 긴 말부터. '큰딸' → 딸, '어머니' → 어머니 (엄마보다 먼저).
_HINTS = (
    ("며느리", "DAUGHTER_IN_LAW"),
    ("사위", "SON_IN_LAW"),
    ("할아버지", "GRANDFATHER"),
    ("할머니", "GRANDMOTHER"),
    ("손주", "GRANDCHILD"),
    ("배우자", "SPOUSE"),
    ("어머니", "MOTHER"),
    ("아버지", "FATHER"),
    ("엄마", "MOTHER"),
    ("아빠", "FATHER"),
    ("남편", "SPOUSE"),
    ("아내", "SPOUSE"),
    ("딸", "DAUGHTER"),
    ("아들", "SON"),
    ("오빠", "BROTHER"),
    ("형", "BROTHER"),
    ("누나", "SISTER"),
    ("언니", "SISTER"),
    ("동생", "OTHER"),
)


def normalize_relation(raw: str | None) -> str | None:
    if raw is None:
        return None
    code = raw.strip().upper().replace("-", "_").replace(" ", "_")
    if not code:
        return None
    return code if code in RELATION_CODES else ""


def guess_relation(label: str | None) -> str:
    if not label:
        return "OTHER"
    compact = label.replace(" ", "")
    for needle, code in _HINTS:
        if needle in compact:
            return code
    return "OTHER"


def resolve_relation(explicit: str | None, label: str | None, proposed: str | None = None,
                     other: str | None = None) -> str:
    """고른 코드 → 부르는 이름에서 짐작 → 상대가 제안한 코드 → 반대말 → 기타."""
    if explicit in RELATION_CODES:
        return explicit
    guessed = guess_relation(label)
    if guessed != "OTHER":
        return guessed
    if proposed in RELATION_CODES:
        return proposed
    if other in RELATION_CODES:
        return INVERSE.get(other, "OTHER")
    return "OTHER"
