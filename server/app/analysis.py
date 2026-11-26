"""사진 받기 → 확인 → 품질 검사 → AI 정리. /api/analyze 와 자녀 대신 보내기가 같이 쓴다.

개인정보: 사진은 요청 처리 동안 메모리에만 두고 디스크·로그에 남기지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from . import quality, router, usage
from .providers import ImageInput, ProviderError, get_provider
from .schema import AnalysisResult

log = logging.getLogger("ilgeodeurim")

MAX_IMAGES = int(os.getenv("MAX_IMAGES", "5"))
MAX_BYTES = int(os.getenv("MAX_IMAGE_MB", "10")) * 1024 * 1024
ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


class AnalyzeError(Exception):
    def __init__(self, status: int, code: str, user_message: str, extra: dict | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.user_message = user_message
        self.extra = extra or {}

    def response(self) -> JSONResponse:
        return JSONResponse(status_code=self.status,
                            content={"error": {"code": self.code, "userMessage": self.user_message, **self.extra}})


def sniff(data: bytes, declared: str | None) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "image/heic"
    return declared if declared in ALLOWED else None


async def read_images(images: list[UploadFile]) -> list[ImageInput]:
    if not images:
        raise AnalyzeError(400, "no_image", "사진이 없어요. 다시 찍어 주세요.")
    if len(images) > MAX_IMAGES:
        raise AnalyzeError(400, "too_many", f"사진은 한 번에 {MAX_IMAGES}장까지 보낼 수 있어요.")
    inputs: list[ImageInput] = []
    for f in images:
        data = await f.read()
        await f.close()
        if not data:
            raise AnalyzeError(400, "empty", "사진이 비어 있어요. 다시 찍어 주세요.")
        if len(data) > MAX_BYTES:
            raise AnalyzeError(413, "too_large", "사진이 너무 커요. 다시 찍어 주세요.")
        mime = sniff(data, f.content_type)
        if mime is None:
            raise AnalyzeError(415, "bad_type", "사진 파일만 보낼 수 있어요.")
        inputs.append(ImageInput(data=data, mime_type=mime, filename=f.filename or ""))
    return inputs


async def check_quality(inputs: list[ImageInput]) -> list[quality.PageResult]:
    """읽을 수 없는 사진이면 422 (AI 를 부르지 않는다). 열 수 없는 형식(HEIC 등)은 건너뛴다."""
    if not quality.enabled():
        return []
    try:
        results = await asyncio.to_thread(quality.check, [i.data for i in inputs])
    except Exception as e:  # Pillow 의 압축 폭탄 오류 등
        log.warning("quality check refused image: %s", type(e).__name__)
        raise AnalyzeError(413, "too_large", "사진이 너무 커요. 다시 찍어 주세요.") from None
    bad = quality.first_failure(results)
    if bad is not None:
        log.info("quality rejected page=%d problems=%s metrics=%s", bad.index, bad.problems,
                 bad.metrics.as_dict() if bad.metrics else None)
        raise AnalyzeError(422, bad.problems[0], quality.user_message(bad, len(inputs)),
                           {"page": bad.index + 1, "problems": bad.problems})
    return results


async def analyze(inputs: list[ImageInput]) -> tuple[AnalysisResult, dict]:
    """(정리 결과, 디버그 정보). 사진 바이트는 끝나면 놓아준다."""
    calls = usage.start()
    t0 = time.monotonic()
    try:
        checked = await check_quality(inputs)
        provider = get_provider()
        raw, doc_type, model = await router.run(provider, inputs)
    except ProviderError as e:
        log.warning("provider error: %s", str(e)[:700].replace("\n", " "))
        raise AnalyzeError(502, "ai_failed", "지금은 서류를 읽을 수 없어요. 잠시 뒤에 다시 해 주세요.") from None
    finally:
        inputs.clear()  # 사진 바이트를 바로 놓아준다

    if raw.get("readable") is False:
        raise AnalyzeError(422, "unreadable", "글씨가 잘 안 보여요. 밝은 곳에서 서류 전체가 나오게 다시 찍어 주세요.")
    try:
        result = AnalysisResult.model_validate({**raw, "model": f"{provider.name}:{model}"})
    except Exception as e:  # 모델이 스키마를 어긴 경우
        log.warning("schema error: %s", str(e)[:200])
        raise AnalyzeError(502, "bad_output", "서류를 정리하다가 문제가 생겼어요. 다시 해 주세요.") from None
    elapsed = time.monotonic() - t0
    log.info("analyzed type=%s model=%s todos=%d %.1fs usage=%s", doc_type, result.model, len(result.todos),
             elapsed, calls)
    debug = {"classifiedAs": doc_type, "seconds": round(elapsed, 2), "calls": calls,
             "quality": [r.metrics.as_dict() if r.metrics else None for r in checked]}
    return result, debug


def debug_enabled() -> bool:
    return os.getenv("DEBUG_USAGE") == "1"  # 비용·속도 측정용. 운영에서는 끈다.
