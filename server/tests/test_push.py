"""푸시: 기기별 발송·기록·죽은 토큰 끄기, FCM HTTP v1 (가짜 전송으로), 설정으로 고르기."""
import asyncio
import base64
import json
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from sqlalchemy import select

from app.auth.models import UserPushToken
from app.family.models import PushLog
from app.push import FakePushSender, FcmPushSender, PushMessage, PushResult, notify_user
from app.push import config as push_config
from conftest import RsaKey, add_push_token, login_fake, run_db

MSG = PushMessage(title="자녀가 서류를 보냈어요", body="큰딸이 고지서를 보냈어요.", data={"type": "DOC_RECEIVED", "n": "1"})


def _notify(sender, user_no, **kw):
    return run_db(lambda s: notify_user(s, sender, user_no, "DOC_RECEIVED", MSG, **kw))


def _logs():
    return run_db(lambda s: s.scalars(select(PushLog).order_by(PushLog.push_log_no)))


def _active_tokens(user_no):
    return {t.push_token for t in run_db(lambda s: s.scalars(select(UserPushToken).where(
        UserPushToken.user_no == user_no, UserPushToken.active_yn.is_(True))))}


# ---------- notify_user ----------

def test_sends_to_every_active_device_and_logs(client):
    u = login_fake(client, "p1")
    add_push_token(client, u, "phone-a")
    add_push_token(client, u, "tablet-b", platform="IOS")
    fake = FakePushSender()
    assert _notify(fake, u["user"]["userNo"], document_no=None, family_link_no=None) == 2
    assert {t for t, _ in fake.sent} == {"phone-a", "tablet-b"}
    logs = _logs()
    assert [r.result_cd for r in logs] == ["SENT", "SENT"]
    assert all(r.sender_cd == "FAKE" and r.event_cd == "DOC_RECEIVED" and r.message_id for r in logs)


def test_no_token_and_disabled_are_logged(client):
    u = login_fake(client, "p2")
    n = u["user"]["userNo"]
    assert _notify(FakePushSender(), n) == 0
    assert _notify(None, n) == 0
    assert [(r.result_cd, r.sender_cd) for r in _logs()] == [("NO_TOKEN", "FAKE"), ("DISABLED", "NONE")]


def test_dead_token_is_turned_off_and_failures_do_not_break(client):
    u = login_fake(client, "p3")
    n = u["user"]["userNo"]
    for t in ("dead", "flaky", "good"):
        add_push_token(client, u, t)
    fake = FakePushSender()
    fake.invalid_tokens.add("dead")
    fake.failing_tokens.add("flaky")
    assert _notify(fake, n) == 1
    assert sorted((r.result_cd, r.error_cd) for r in _logs()) == [
        ("FAILED", "UNAVAILABLE"), ("INVALID_TOKEN", "UNREGISTERED"), ("SENT", None)]
    assert _active_tokens(n) == {"flaky", "good"}
    _notify(fake, n)  # 꺼진 토큰에는 다시 보내지 않는다
    assert [t for t, _ in fake.sent].count("good") == 2 and "dead" not in [t for t, _ in fake.sent]


class Crashing:
    code = "CRASH"

    async def send(self, token, message):
        raise ZeroDivisionError("boom")


class Slow:
    code = "SLOW"

    async def send(self, token, message):
        await asyncio.sleep(5)
        return PushResult(True)


def test_sender_crash_or_timeout_never_raises(client):
    u = login_fake(client, "p4")
    add_push_token(client, u, "phone")
    n = u["user"]["userNo"]
    assert _notify(Crashing(), n) == 0
    assert run_db(lambda s: notify_user(s, Slow(), n, "X", MSG, timeout_s=0.05)) == 0
    assert [(r.result_cd, r.error_cd) for r in _logs()] == [("FAILED", "ZeroDivisionError"), ("FAILED", "TIMEOUT")]
    assert _active_tokens(n) == {"phone"}


# ---------- FCM HTTP v1 ----------

KEY = RsaKey("fcm-kid")
SA = {
    "type": "service_account", "project_id": "demo-proj", "private_key_id": "fcm-kid",
    "private_key": KEY.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()).decode(),
    "client_email": "push@demo-proj.iam.gserviceaccount.com", "token_uri": "https://oauth2.googleapis.com/token",
}
SEND_URL = "https://fcm.googleapis.com/v1/projects/demo-proj/messages:send"


class FcmFake:
    """oauth2 와 fcm 을 흉내 낸다. send_replies 를 차례로 돌려준다."""

    def __init__(self, *send_replies: httpx.Response):
        self.replies = list(send_replies)
        self.token_calls: list[dict] = []
        self.sends: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if str(req.url) == SA["token_uri"]:
            form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
            self.token_calls.append(form)
            return httpx.Response(200, json={"access_token": f"ya29.t{len(self.token_calls)}", "expires_in": 3599})
        assert str(req.url) == SEND_URL
        self.sends.append(req)
        return self.replies.pop(0) if self.replies else httpx.Response(200, json={"name": "projects/demo-proj/messages/1"})


def _sender(fake: FcmFake) -> FcmPushSender:
    return FcmPushSender(SA, transport=httpx.MockTransport(fake))


def _fcm_error(status: int, code: str, *, error_code: str | None = None, field: str | None = None):
    details = []
    if error_code:
        details.append({"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": error_code})
    if field:
        details.append({"@type": "type.googleapis.com/google.rpc.BadRequest",
                        "fieldViolations": [{"field": field, "description": "bad"}]})
    return httpx.Response(status, json={"error": {"code": status, "status": code, "details": details}})


def test_fcm_signs_assertion_and_sends_v1_payload():
    fake = FcmFake()
    s = _sender(fake)
    r = asyncio.run(s.send("device-token-1", MSG))
    assert r.ok and r.message_id == "projects/demo-proj/messages/1"

    form = fake.token_calls[0]
    assert form["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    claims = jwt.decode(form["assertion"], KEY.public_pem, algorithms=["RS256"], audience=SA["token_uri"])
    assert claims["iss"] == SA["client_email"]
    assert claims["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
    assert claims["exp"] - claims["iat"] == 3600
    assert jwt.get_unverified_header(form["assertion"])["kid"] == "fcm-kid"

    req = fake.sends[0]
    assert req.headers["authorization"] == "Bearer ya29.t1"
    body = json.loads(req.content)["message"]
    assert body["token"] == "device-token-1"
    assert body["notification"] == {"title": MSG.title, "body": MSG.body}
    assert body["data"] == {"type": "DOC_RECEIVED", "n": "1"}
    assert body["android"]["priority"] == "HIGH" and body["android"]["notification"]["channel_id"] == "family"
    assert body["apns"]["payload"]["aps"]["sound"] == "default"


def test_fcm_reuses_access_token():
    fake = FcmFake()
    s = _sender(fake)

    async def twice():
        await s.send("a", MSG)
        await s.send("b", MSG)
    asyncio.run(twice())
    assert len(fake.token_calls) == 1 and len(fake.sends) == 2


def test_fcm_retries_once_on_401_with_fresh_token():
    fake = FcmFake(_fcm_error(401, "UNAUTHENTICATED"))
    r = asyncio.run(_sender(fake).send("a", MSG))
    assert r.ok
    assert len(fake.token_calls) == 2
    assert [q.headers["authorization"] for q in fake.sends] == ["Bearer ya29.t1", "Bearer ya29.t2"]


@pytest.mark.parametrize("reply,code,dead", [
    (_fcm_error(404, "NOT_FOUND", error_code="UNREGISTERED"), "UNREGISTERED", True),
    (_fcm_error(403, "PERMISSION_DENIED", error_code="SENDER_ID_MISMATCH"), "SENDER_ID_MISMATCH", True),
    (_fcm_error(400, "INVALID_ARGUMENT", error_code="INVALID_ARGUMENT", field="message.token"), "INVALID_ARGUMENT", True),
    (_fcm_error(400, "INVALID_ARGUMENT", error_code="INVALID_ARGUMENT", field="message.data"), "INVALID_ARGUMENT", False),
    (_fcm_error(429, "RESOURCE_EXHAUSTED", error_code="QUOTA_EXCEEDED"), "QUOTA_EXCEEDED", False),
    (_fcm_error(503, "UNAVAILABLE", error_code="UNAVAILABLE"), "UNAVAILABLE", False),
    (httpx.Response(500, text="<html>oops</html>"), "HTTP_500", False),
])
def test_fcm_error_mapping(reply, code, dead):
    r = asyncio.run(_sender(FcmFake(reply)).send("a", MSG))
    assert (r.ok, r.error, r.invalid_token) == (False, code, dead)


def test_fcm_oauth_failure_is_a_soft_failure():
    def handler(req):
        return httpx.Response(400, json={"error": "invalid_grant"})
    r = asyncio.run(FcmPushSender(SA, transport=httpx.MockTransport(handler)).send("a", MSG))
    assert r.ok is False and r.invalid_token is False and r.error == "RuntimeError"


def test_fcm_rejects_incomplete_service_account():
    with pytest.raises(ValueError):
        FcmPushSender({"client_email": "x"})
    with pytest.raises(ValueError):
        FcmPushSender({**SA, "project_id": ""})
    assert FcmPushSender({**SA, "project_id": ""}, project_id="other").project_id == "other"


# ---------- 설정 ----------

def test_config_picks_sender(env, tmp_path):
    assert push_config.build_sender() is None  # 키가 없으면 조용히 끔
    env.set(PUSH_PROVIDER="fake")
    assert isinstance(push_config.build_sender(), FakePushSender)
    env.set(PUSH_PROVIDER="none")
    assert push_config.build_sender() is None

    env.set(PUSH_PROVIDER="fcm")
    with pytest.raises(RuntimeError):
        push_config.build_sender()

    path = tmp_path / "sa.json"
    path.write_text(json.dumps(SA), encoding="utf-8")
    env.set(FCM_SERVICE_ACCOUNT_FILE=str(path))
    s = push_config.build_sender()
    assert isinstance(s, FcmPushSender) and s.project_id == "demo-proj"

    env.mp.delenv("FCM_SERVICE_ACCOUNT_FILE")
    env.mp.delenv("PUSH_PROVIDER")
    env.set(FCM_SERVICE_ACCOUNT_JSON=base64.b64encode(json.dumps(SA).encode()).decode(), FCM_PROJECT_ID="override")
    s = push_config.build_sender()
    assert isinstance(s, FcmPushSender) and s.project_id == "override"

    env.set(FCM_SERVICE_ACCOUNT_JSON="!!!not-base64!!!")
    with pytest.raises(RuntimeError):
        push_config.build_sender()


def test_get_sender_is_cached_until_reset(env):
    env.set(PUSH_PROVIDER="fake")
    a = push_config.get_sender()
    assert push_config.get_sender() is a
    push_config.reset_sender()
    assert push_config.get_sender() is not a
