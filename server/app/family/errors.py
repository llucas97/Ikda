"""가족·서류 오류. 응답 모양은 다른 API 와 같다: {"error": {"code", "userMessage"}} (AuthError 처리기를 같이 쓴다)."""
from __future__ import annotations

from ..auth.errors import AuthError


class FamilyError(AuthError):
    pass


def link_not_found() -> FamilyError:
    return FamilyError(404, "link_not_found", "가족 연결을 찾을 수 없어요.")


def invite_invalid() -> FamilyError:
    return FamilyError(404, "invite_invalid", "번호가 맞지 않거나 시간이 지났어요. 새 번호를 받아 주세요.")


def document_not_found() -> FamilyError:
    return FamilyError(404, "document_not_found", "서류를 찾을 수 없어요.")
