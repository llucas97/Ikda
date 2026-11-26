"""읽어드림 서버. POST /api/analyze (multipart: images=사진 여러 장)

개인정보: 사진은 요청 처리 동안 메모리에만 두고 디스크·로그에 남기지 않는다.
"""
from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import analysis
from .analysis import MAX_BYTES, MAX_IMAGES  # noqa: F401  (예전 import 경로)
from .auth import routes as auth_routes
from .auth.deps import AuthContext, optional_auth
from .db import session_scope
from .family import documents
from .family import routes as family_routes
from .providers import get_provider

log = logging.getLogger("ilgeodeurim")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="읽다 API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)
auth_routes.install(app)
family_routes.install(app)


def _err(status: int, code: str, msg: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "userMessage": msg}})


@app.get("/health")
async def health():
    p = get_provider()
    return {"ok": True, "provider": p.name}


def _sha_list() -> list[str]:
    raw = os.getenv("ANDROID_CERT_SHA256", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


@app.get("/.well-known/assetlinks.json")
async def assetlinks():
    """Android App Links. 서명 SHA-256 은 ANDROID_CERT_SHA256 (쉼표로 여러 개)."""
    fingerprints = _sha_list()
    body = []
    if fingerprints:
        body.append({
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {"namespace": "android_app", "package_name": "com.ilgeodeurim.ilgeodeurim",
                       "sha256_cert_fingerprints": fingerprints},
        })
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/.well-known/apple-app-site-association")
@app.get("/apple-app-site-association")
async def apple_app_site_association():
    """iOS Universal Links. APPLE_TEAM_ID 가 없으면 자리만 둔다."""
    team = os.getenv("APPLE_TEAM_ID", "").strip() or "TEAMID"
    return JSONResponse({
        "applinks": {"apps": [], "details": [{
            "appID": f"{team}.com.ilgeodeurim.ilgeodeurim",
            "paths": ["/f/*"],
        }]},
    }, headers={"Cache-Control": "public, max-age=3600"})


def _analyze_requires_login() -> bool:
    return os.getenv("AUTH_REQUIRED_FOR_ANALYZE") == "1"


@app.post("/api/analyze")
async def analyze(images: list[UploadFile] = File(...), save: bool = Form(False),
                  auth: AuthContext | None = Depends(optional_auth)):
    # 기본은 끈다. 토큰이 없으면 DB 도 열지 않는다. 있는데 틀리면 플래그와 상관없이 401.
    if _analyze_requires_login() and auth is None:
        return _err(401, "login_required", "로그인해 주세요.")
    try:
        inputs = await analysis.read_images(images)
        pages = len(inputs)
        result, debug = await analysis.analyze(inputs)
    except analysis.AnalyzeError as e:
        return e.response()

    out = result.model_dump()
    if save and auth is not None:
        # 로그인했으면 결과(글)만 서버에 보관해 다른 기기·가족과 맞춘다. 사진은 두지 않는다.
        async with session_scope() as db:
            doc = await documents.store_result(db, auth.user, result, page_count=pages)
            out = await documents.visible_json(db, documents.Visible(doc, "OWNER"))
        out["saved"] = True
    elif save:
        out["saved"] = False
    if analysis.debug_enabled():
        out["debug"] = debug
    return out
