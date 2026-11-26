"""어떤 발송 수단을 쓸지 환경변수로 정한다. 키는 코드·저장소에 두지 않는다.

  PUSH_PROVIDER            fcm | fake | none   (비우면: FCM 서비스 계정이 있으면 fcm, 없으면 none)
  FCM_SERVICE_ACCOUNT_FILE 서비스 계정 JSON 파일 경로 (GOOGLE_APPLICATION_CREDENTIALS 도 받음)
  FCM_SERVICE_ACCOUNT_JSON 파일 대신 JSON 문자열 (또는 base64)
  FCM_PROJECT_ID           비우면 서비스 계정의 project_id
  PUSH_TIMEOUT_S           한 번 보내기 제한 시간 (기본 5)
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from pathlib import Path

from .base import PushSender
from .fake import FakePushSender
from .fcm import FcmPushSender

log = logging.getLogger("ilgeodeurim.push")

_sender: PushSender | None = None
_loaded = False


def _service_account() -> dict | None:
    raw = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        if not raw.startswith("{"):
            try:
                raw = base64.b64decode(raw).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                raise RuntimeError("FCM_SERVICE_ACCOUNT_JSON 을 읽을 수 없어요 (JSON 또는 base64)") from None
        return json.loads(raw)
    path = os.getenv("FCM_SERVICE_ACCOUNT_FILE", "").strip() or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return None


def build_sender() -> PushSender | None:
    provider = os.getenv("PUSH_PROVIDER", "").strip().lower()
    if provider == "none":
        return None
    if provider == "fake":
        log.warning("PUSH_PROVIDER=fake — 푸시를 실제로 보내지 않아요.")
        return FakePushSender()
    sa = _service_account()
    if sa is None:
        if provider == "fcm":
            raise RuntimeError("PUSH_PROVIDER=fcm 인데 FCM 서비스 계정이 없어요 (FCM_SERVICE_ACCOUNT_FILE)")
        return None
    return FcmPushSender(sa, project_id=os.getenv("FCM_PROJECT_ID", "").strip() or None,
                         timeout_s=float(os.getenv("PUSH_TIMEOUT_S", "5")))


def get_sender() -> PushSender | None:
    global _sender, _loaded
    if not _loaded:
        _sender = build_sender()
        _loaded = True
    return _sender


def reset_sender() -> None:
    global _sender, _loaded
    _sender, _loaded = None, False


def push_sender_dep() -> PushSender | None:
    """FastAPI 의존성. 테스트는 app.dependency_overrides[push_sender_dep] 로 FakePushSender 를 넣는다."""
    return get_sender()
