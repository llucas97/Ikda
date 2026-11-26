"""가족 연결·서류 API. 계약은 docs/phase3-plan.md §2.

  POST   /api/family/invites                  초대 만들기 (6자리 번호 + 링크)
  DELETE /api/family/invites/{inviteId}       초대 취소
  POST   /api/family/invites/preview          누가 보낸 초대인지 (수락 전)
  POST   /api/family/invites/accept           한 번 눌러 수락
  GET    /api/family                          내 가족·기다리는 초대
  PATCH  /api/family/links/{linkId}           상대를 부르는 이름
  DELETE /api/family/links/{linkId}           연결 끊기 (어느 쪽이든)
  POST   /api/family/links/{linkId}/analyze   자녀가 어르신 대신 찍어 보내기 (multipart images)
  GET    /api/family/documents                자녀 화면: 보냈거나 나눠 받은 서류
  GET    /api/documents                       내 서류 (?since= 동기화)
  POST   /api/documents                       기기 저장본 올리기
  GET    /api/documents/{id}                  한 건 (주인 또는 권한 있는 자녀)
  DELETE /api/documents/{id}                  지우기 (주인)
  PATCH  /api/documents/{id}/todos/{todoId}   할 일 다 함·알림 (주인)
  POST   /api/documents/{id}/seen             열어 봄 (주인)
  POST   /api/documents/{id}/shares           자녀에게 보내기 (주인 = 연결의 어르신)
  DELETE /api/documents/{id}/shares/{linkId}  나눔 거두기
  GET    /f/{token}                           초대 링크 → 앱 열기 안내 페이지
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import analysis
from ..auth.config import AuthSettings
from ..auth.deps import AuthContext, client_ip, current_auth, settings_dep
from ..db import get_session
from ..push import PushSender, notify_user, push_sender_dep
from . import documents, notify, service
from .config import FamilySettings, get_family_settings
from .documents import DocumentIn, iso_utc
from .relations import RELATION_KO

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}
APP_JOIN = "ilgeodeurim://family/join"


def family_settings_dep() -> FamilySettings:
    return get_family_settings()


class InviteBody(BaseModel):
    myRole: Literal["SENIOR", "CHILD"] | None = None
    label: str | None = Field(default=None, max_length=30)  # 내가 상대를 부를 별명 (예: 엄마, 큰딸)
    relationCd: str | None = Field(default=None, max_length=20)  # 내가 상대를 보는 관계
    counterRelationCd: str | None = Field(default=None, max_length=20)  # 상대가 나를 보도록 제안
    counterNickname: str | None = Field(default=None, max_length=30)


class InviteUseBody(BaseModel):
    code: str | None = Field(default=None, max_length=20)
    token: str | None = Field(default=None, max_length=100)
    label: str | None = Field(default=None, max_length=30)  # 수락: 초대한 사람을 부를 이름
    relationCd: str | None = Field(default=None, max_length=20)  # 수락: 내가 상대를 보는 관계


class LabelBody(BaseModel):
    label: str | None = Field(default=None, max_length=30)
    relationCd: str | None = Field(default=None, max_length=20)


class PermissionBody(BaseModel):
    canView: bool | None = None
    canEdit: bool | None = None
    canDelete: bool | None = None
    notification: bool | None = None


class TodoPatch(BaseModel):
    done: bool | None = None
    remind: bool | None = None


class ShareBody(BaseModel):
    linkIds: list[int] | None = Field(default=None, max_length=10)


def link_json(v: service.LinkView) -> dict:
    return {
        "linkId": v.link.family_link_no,
        "myRole": v.my_role,
        "member": {"role": "CHILD" if v.my_role == "SENIOR" else "SENIOR", "name": v.other.name,
                   "label": v.other_label, "profileImageUrl": v.other.profile_image_url},
        "linkedAt": iso_utc(v.link.linked_at),
        "relationCd": v.relation_cd,
        "relationLabel": RELATION_KO.get(v.relation_cd, "가족"),
        "nickname": v.nickname or v.other_label,
        "mappingId": v.mapping_no,
        "isPrimary": v.is_primary,
        "permissions": {"canView": v.can_view, "canEdit": v.can_edit, "canDelete": v.can_delete,
                        "notification": v.notification},
        "canSend": v.can_send,
    }


def _bad_input() -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": {
        "code": "invite_missing", "userMessage": "번호 6자리를 넣어 주세요."}})


# ---------- 초대 ----------

@router.post("/api/family/invites", status_code=201)
async def create_invite(request: Request, body: InviteBody | None = None, auth: AuthContext = Depends(current_auth),
                        db: AsyncSession = Depends(get_session), s: AuthSettings = Depends(settings_dep),
                        fs: FamilySettings = Depends(family_settings_dep)):
    body = body or InviteBody()
    new = await service.create_invite(db, s, fs, auth.user, role=body.myRole, label=body.label,
                                      ip=client_ip(request), relation=body.relationCd,
                                      counter_relation=body.counterRelationCd, counter_nickname=body.counterNickname)
    web = f"{s.public_base_url.rstrip('/')}/f/{new.token}"
    minutes = fs.invite_ttl_s // 60
    pretty = f"{new.code[:3]} {new.code[3:]}"
    return JSONResponse(status_code=201, headers=NO_STORE, content={
        "inviteId": new.invite.invite_no,
        "code": new.code,
        "myRole": new.invite.inviter_role_cd,
        "expiresAt": iso_utc(new.invite.expires_at),
        "expiresInSeconds": fs.invite_ttl_s,
        "appLink": f"{APP_JOIN}?t={new.token}",
        "webLink": web,
        "shareText": (f"읽다에서 가족으로 연결해요.\n아래 주소를 누르거나, 앱에서 번호 {pretty} 을 넣어 주세요.\n"
                      f"{web}\n({minutes}분 동안만 쓸 수 있어요)"),
    })


@router.delete("/api/family/invites/{invite_no}", status_code=204)
async def cancel_invite(invite_no: int, request: Request, auth: AuthContext = Depends(current_auth),
                        db: AsyncSession = Depends(get_session)):
    await service.cancel_invite(db, auth.user, invite_no, ip=client_ip(request))
    return Response(status_code=204)


@router.post("/api/family/invites/preview")
async def preview_invite(body: InviteUseBody, request: Request, auth: AuthContext = Depends(current_auth),
                         db: AsyncSession = Depends(get_session), s: AuthSettings = Depends(settings_dep),
                         fs: FamilySettings = Depends(family_settings_dep)):
    if not body.code and not body.token:
        return _bad_input()
    out = await service.preview_invite(db, s, fs, auth.user, code=body.code, token=body.token,
                                       ip=client_ip(request))
    out["expiresAt"] = iso_utc(out["expiresAt"])
    return JSONResponse(out, headers=NO_STORE)


@router.post("/api/family/invites/accept")
async def accept_invite(body: InviteUseBody, request: Request, auth: AuthContext = Depends(current_auth),
                        db: AsyncSession = Depends(get_session), s: AuthSettings = Depends(settings_dep),
                        fs: FamilySettings = Depends(family_settings_dep),
                        sender: PushSender | None = Depends(push_sender_dep)):
    if not body.code and not body.token:
        return _bad_input()
    view, invite = await service.accept_invite(db, s, fs, auth.user, code=body.code, token=body.token,
                                               label=body.label, relation=body.relationCd, ip=client_ip(request))
    # 초대한 사람에게: 누가 수락했는지 (잘못된 사람이면 바로 끊을 수 있게)
    inviter_view = service.LinkView(view.link, "SENIOR" if view.my_role == "CHILD" else "CHILD", auth.user)
    if await service.wants_push(db, invite.inviter_user_no, auth.user.user_no):
        await notify_user(db, sender, invite.inviter_user_no, "FAMILY_LINKED",
                          notify.family_linked(inviter_view.other_label, view.link.family_link_no),
                          family_link_no=view.link.family_link_no)
    return JSONResponse({"link": link_json(view)}, headers=NO_STORE)


# ---------- 가족 ----------

@router.get("/api/family")
async def family(auth: AuthContext = Depends(current_auth), db: AsyncSession = Depends(get_session)):
    views, pending = await service.list_family(db, auth.user)
    return JSONResponse(headers=NO_STORE, content={
        "links": [link_json(v) for v in views],
        "pendingInvite": ({"inviteId": pending.invite_no, "myRole": pending.inviter_role_cd,
                           "expiresAt": iso_utc(pending.expires_at)} if pending else None),
    })


@router.patch("/api/family/links/{link_no}")
async def set_label(link_no: int, body: LabelBody, request: Request, auth: AuthContext = Depends(current_auth),
                    db: AsyncSession = Depends(get_session)):
    view = await service.set_label(db, auth.user, link_no, body.label, relation=body.relationCd,
                                  update_label="label" in body.model_fields_set, ip=client_ip(request))
    return JSONResponse({"link": link_json(view)}, headers=NO_STORE)


@router.patch("/api/family/links/{link_no}/permissions")
async def set_permissions(link_no: int, body: PermissionBody, request: Request,
                          auth: AuthContext = Depends(current_auth), db: AsyncSession = Depends(get_session)):
    view = await service.set_permissions(db, auth.user, link_no, can_view=body.canView, can_edit=body.canEdit,
                                        can_delete=body.canDelete, notification=body.notification,
                                        ip=client_ip(request))
    return JSONResponse({"link": link_json(view)}, headers=NO_STORE)


@router.delete("/api/family/links/{link_no}", status_code=204)
async def unlink(link_no: int, request: Request, auth: AuthContext = Depends(current_auth),
                 db: AsyncSession = Depends(get_session)):
    await service.unlink(db, auth.user, link_no, ip=client_ip(request))
    return Response(status_code=204)


@router.post("/api/family/links/{link_no}/analyze", status_code=201)
async def send_on_behalf(link_no: int, request: Request, images: list[UploadFile] = File(...),
                         auth: AuthContext = Depends(current_auth), db: AsyncSession = Depends(get_session),
                         fs: FamilySettings = Depends(family_settings_dep),
                         sender: PushSender | None = Depends(push_sender_dep)):
    await documents.check_can_send(db, fs, auth.user, link_no)
    await db.commit()  # AI 를 기다리는 동안 DB 연결을 잡고 있지 않게
    try:
        inputs = await analysis.read_images(images)
        pages = len(inputs)
        result, debug = await analysis.analyze(inputs)
    except analysis.AnalyzeError as e:
        return e.response()
    doc, view = await documents.store_sent(db, auth.user, link_no, result, page_count=pages, ip=client_ip(request))
    pushed = 0
    if await service.wants_push(db, view.other.user_no, auth.user.user_no):
        pushed = await notify_user(db, sender, view.other.user_no, "DOC_RECEIVED",
                                   notify.doc_received(doc.sender_label or "자녀", doc.doc_type_cd, doc.document_uid,
                                                       link_no),
                                   document_no=doc.document_no, family_link_no=link_no)
    out = await documents.visible_json(db, documents.Visible(doc, "FAMILY", view.link))
    out["pushed"] = pushed
    if analysis.debug_enabled():
        out["debug"] = debug
    return JSONResponse(status_code=201, content=out, headers=NO_STORE)


@router.get("/api/family/documents")
async def family_documents(auth: AuthContext = Depends(current_auth), db: AsyncSession = Depends(get_session)):
    return JSONResponse({"documents": await documents.list_family_documents(db, auth.user)}, headers=NO_STORE)


# ---------- 서류 ----------

@router.get("/api/documents")
async def my_documents(since: datetime | None = Query(default=None), auth: AuthContext = Depends(current_auth),
                       db: AsyncSession = Depends(get_session)):
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    server_time = datetime.now(timezone.utc)
    docs, deleted = await documents.list_owned(db, auth.user.user_no, since)
    return JSONResponse({"documents": docs, "deleted": deleted, "serverTime": iso_utc(server_time)},
                        headers=NO_STORE)


@router.post("/api/documents")
async def import_document(body: DocumentIn, auth: AuthContext = Depends(current_auth),
                          db: AsyncSession = Depends(get_session)):
    doc, created = await documents.import_document(db, auth.user, body)
    out = await documents.visible_json(db, documents.Visible(doc, "OWNER"))
    return JSONResponse(status_code=201 if created else 200, content=out, headers=NO_STORE)


@router.get("/api/documents/{uid}")
async def get_document(uid: str, request: Request, auth: AuthContext = Depends(current_auth),
                       db: AsyncSession = Depends(get_session)):
    v = await documents.get_visible(db, auth.user, uid, ip=client_ip(request))
    return JSONResponse(await documents.visible_json(db, v), headers=NO_STORE)


@router.delete("/api/documents/{uid}", status_code=204)
async def delete_document(uid: str, request: Request, auth: AuthContext = Depends(current_auth),
                          db: AsyncSession = Depends(get_session)):
    await documents.delete_document(db, auth.user, uid, ip=client_ip(request))
    return Response(status_code=204)


@router.patch("/api/documents/{uid}/todos/{todo_uid}")
async def update_todo(uid: str, todo_uid: str, body: TodoPatch, request: Request,
                      auth: AuthContext = Depends(current_auth), db: AsyncSession = Depends(get_session),
                      sender: PushSender | None = Depends(push_sender_dep)):
    todo, doc, tell_owner = await documents.update_todo(db, auth.user, uid, todo_uid, done=body.done,
                                                       remind=body.remind, ip=client_ip(request))
    if tell_owner and body.done is True and await service.wants_push(db, doc.owner_user_no, auth.user.user_no):
        who = doc.sender_label or "가족"
        await notify_user(db, sender, doc.owner_user_no, "TODO_DONE",
                          notify.todo_done(who, doc.document_uid, doc.family_link_no or 0),
                          document_no=doc.document_no, family_link_no=doc.family_link_no)
    return JSONResponse(documents.todo_json(todo), headers=NO_STORE)


@router.post("/api/documents/{uid}/seen", status_code=204)
async def mark_seen(uid: str, request: Request, auth: AuthContext = Depends(current_auth),
                    db: AsyncSession = Depends(get_session)):
    await documents.mark_seen(db, auth.user, uid, ip=client_ip(request))
    return Response(status_code=204)


@router.post("/api/documents/{uid}/shares")
async def share_document(uid: str, request: Request, body: ShareBody | None = None,
                         auth: AuthContext = Depends(current_auth), db: AsyncSession = Depends(get_session),
                         sender: PushSender | None = Depends(push_sender_dep)):
    doc, results = await documents.share(db, auth.user, uid, body.linkIds if body else None, ip=client_ip(request))
    shared_to = []
    for view, new in results:
        pushed = 0
        if new and await service.wants_push(db, view.other.user_no, auth.user.user_no):
            senior_label = service.label_of_senior(view.link, auth.user)
            pushed = await notify_user(db, sender, view.other.user_no, "DOC_SHARED",
                                       notify.doc_shared(senior_label, doc.doc_type_cd, doc.document_uid,
                                                         view.link.family_link_no),
                                       document_no=doc.document_no, family_link_no=view.link.family_link_no)
        shared_to.append({"linkId": view.link.family_link_no, "label": view.other_label, "new": new,
                          "pushed": pushed})
    return JSONResponse({"sharedTo": shared_to}, headers=NO_STORE)


@router.delete("/api/documents/{uid}/shares/{link_no}", status_code=204)
async def unshare_document(uid: str, link_no: int, request: Request, auth: AuthContext = Depends(current_auth),
                           db: AsyncSession = Depends(get_session)):
    await documents.unshare(db, auth.user, uid, link_no, ip=client_ip(request))
    return Response(status_code=204)


# ---------- 초대 링크 페이지 ----------

_TOKEN_OK = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


@router.get("/f/{token}", response_class=HTMLResponse)
async def invite_page(token: str):
    """카카오톡·문자에서 누르는 https 주소. DB 를 보지 않는다(토큰이 맞는지 알려 주지 않는다)."""
    if not _TOKEN_OK.match(token):
        return HTMLResponse("<!doctype html><meta charset=utf-8><p>주소가 올바르지 않아요.</p>", status_code=404)
    app_url = html.escape(f"{APP_JOIN}?t={token}", quote=True)
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>읽다 가족 연결</title>
<style>body{{font-family:sans-serif;background:#FFFDF8;color:#1F1D1A;margin:0;padding:32px 20px;text-align:center}}
h1{{font-size:28px}}p{{font-size:20px;line-height:1.6}}
a.btn{{display:block;margin:32px auto;max-width:360px;padding:20px;border-radius:12px;background:#1F1D1A;color:#FFFDF8;
font-size:24px;font-weight:700;text-decoration:none}}</style></head>
<body><h1>읽다 가족 연결</h1>
<p>아래 버튼을 누르면 읽다 앱이 열려요.<br>앱에서 <b>연결하기</b>를 한 번 눌러 주세요.</p>
<a class="btn" href="{app_url}">앱에서 열기</a>
<p>앱이 없으면 먼저 설치한 뒤 이 주소를 다시 눌러 주세요.</p></body></html>"""
    return HTMLResponse(page, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


def install(app: FastAPI) -> None:
    """auth_routes.install(app) 다음에 부른다 (오류 처리기는 AuthError 것을 같이 쓴다)."""
    app.include_router(router)
