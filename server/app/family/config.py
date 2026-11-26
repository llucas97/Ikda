from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    v = os.getenv(name, "").strip()
    return int(v) if v else default


@dataclass(frozen=True)
class FamilySettings:
    invite_ttl_s: int = 30 * 60
    max_children: int = 10  # 어르신 한 분에 연결할 수 있는 자녀 수
    max_seniors: int = 4  # 자녀 한 명이 연결할 수 있는 어르신 수 (양가 부모님)
    fail_window_s: int = 15 * 60
    fail_limit_user: int = 10  # 초대 번호를 이 시간 안에 이만큼 틀리면 잠깐 막는다
    fail_limit_ip: int = 30
    send_daily_limit: int = 30  # 자녀 한 명이 한 어르신께 하루에 대신 보낼 수 있는 서류 수


def get_family_settings() -> FamilySettings:
    return FamilySettings(
        invite_ttl_s=_int("FAMILY_INVITE_TTL_MIN", 30) * 60,
        max_children=_int("FAMILY_MAX_CHILDREN", 10),
        max_seniors=_int("FAMILY_MAX_SENIORS", 4),
        fail_window_s=_int("FAMILY_FAIL_WINDOW_MIN", 15) * 60,
        fail_limit_user=_int("FAMILY_FAIL_LIMIT", 10),
        fail_limit_ip=_int("FAMILY_FAIL_LIMIT_IP", 30),
        send_daily_limit=_int("FAMILY_SEND_DAILY_LIMIT", 30),
    )
