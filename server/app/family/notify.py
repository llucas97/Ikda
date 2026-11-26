"""가족 푸시 문구. 잠금 화면에 보이므로 서류 제목·금액 같은 내용은 넣지 않고 종류만 쓴다."""
from __future__ import annotations

from ..push import PushMessage
from .service import josa

TYPE_LABELS = {"bill": "고지서", "medicine": "약 안내", "hospital": "병원 안내", "contract": "계약서",
               "government": "관공서 서류", "other": "서류"}


def doc_received(child_label: str, doc_type: str, doc_uid: str, link_no: int) -> PushMessage:
    kind = TYPE_LABELS.get(doc_type, "서류")
    return PushMessage(
        title="자녀가 서류를 보냈어요",
        body=f"{josa(child_label, '이', '가')} {josa(kind, '을', '를')} 보냈어요. 눌러서 확인해 주세요.",
        data={"type": "DOC_RECEIVED", "documentId": doc_uid, "linkId": str(link_no)},
    )


def doc_shared(senior_label: str, doc_type: str, doc_uid: str, link_no: int) -> PushMessage:
    kind = TYPE_LABELS.get(doc_type, "서류")
    return PushMessage(
        title=f"{josa(senior_label, '이', '가')} 서류를 보냈어요",
        body=f"{josa(kind, '을', '를')} 같이 봐 달래요. 눌러서 확인해 보세요.",
        data={"type": "DOC_SHARED", "documentId": doc_uid, "linkId": str(link_no)},
    )


def todo_done(who: str, doc_uid: str, link_no: int) -> PushMessage:
    return PushMessage(
        title="할 일을 마쳤대요",
        body=f"{josa(who, '이', '가')} 할 일을 마쳤다고 했어요.",
        data={"type": "TODO_DONE", "documentId": doc_uid, "linkId": str(link_no)},
    )


def family_linked(other_label: str, link_no: int) -> PushMessage:
    return PushMessage(
        title="가족 연결이 됐어요",
        body=f"{josa(other_label, '과', '와')} 연결됐어요.",
        data={"type": "FAMILY_LINKED", "linkId": str(link_no)},
    )
