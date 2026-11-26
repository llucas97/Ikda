"""FCM HTTP v1 발송. 서비스 계정 키(JSON)로 OAuth 토큰을 받아 보낸다 (google-auth 없이 PyJWT 로).

  POST https://oauth2.googleapis.com/token   grant_type=jwt-bearer, assertion=RS256(서비스 계정)
  POST https://fcm.googleapis.com/v1/projects/{project}/messages:send   Bearer 위 토큰

iOS 도 FCM 토큰으로 보낸다 (Firebase 콘솔에 APNs 인증 키를 올려 두어야 한다).
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx
import jwt

from .base import PushMessage, PushResult

log = logging.getLogger("ilgeodeurim.push")

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
# 이 코드들은 토큰이 우리 앱에서 더는 쓸 수 없다는 뜻이다 → 토큰을 끈다.
DEAD_TOKEN_CODES = {"UNREGISTERED", "SENDER_ID_MISMATCH"}


class FcmPushSender:
    code = "FCM"

    def __init__(self, service_account: dict, *, project_id: str | None = None, timeout_s: float = 5.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        for k in ("client_email", "private_key"):
            if not service_account.get(k):
                raise ValueError(f"FCM 서비스 계정에 {k} 가 없어요")
        self.sa = service_account
        self.project_id = project_id or service_account.get("project_id") or ""
        if not self.project_id:
            raise ValueError("FCM_PROJECT_ID 가 없어요")
        self.token_uri = service_account.get("token_uri") or DEFAULT_TOKEN_URI
        self.timeout_s = timeout_s
        self._transport = transport
        self._access: tuple[str, float] | None = None  # (토큰, 만료 시각 monotonic)
        self._lock = asyncio.Lock()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_s), transport=self._transport)

    async def _access_token(self, client: httpx.AsyncClient, *, force: bool = False) -> str:
        async with self._lock:
            now = time.monotonic()
            if not force and self._access and self._access[1] - 60 > now:
                return self._access[0]
            iat = int(time.time())
            assertion = jwt.encode(
                {"iss": self.sa["client_email"], "scope": SCOPE, "aud": self.token_uri, "iat": iat, "exp": iat + 3600},
                self.sa["private_key"], algorithm="RS256",
                headers={"kid": self.sa["private_key_id"]} if self.sa.get("private_key_id") else None,
            )
            r = await client.post(self.token_uri, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
            if r.status_code != 200:
                raise RuntimeError(f"fcm oauth {r.status_code}")
            body = r.json()
            self._access = (body["access_token"], now + int(body.get("expires_in", 3600)))
            return self._access[0]

    def _payload(self, token: str, m: PushMessage) -> dict:
        return {"message": {
            "token": token,
            "notification": {"title": m.title, "body": m.body},
            "data": {k: str(v) for k, v in m.data.items()},
            "android": {"priority": "HIGH", "notification": {"channel_id": "family", "sound": "default"}},
            "apns": {"headers": {"apns-priority": "10"}, "payload": {"aps": {"sound": "default"}}},
        }}

    async def send(self, token: str, message: PushMessage) -> PushResult:
        url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
        try:
            async with self._client() as client:
                access = await self._access_token(client)
                r = await client.post(url, json=self._payload(token, message),
                                      headers={"Authorization": f"Bearer {access}"})
                if r.status_code == 401:  # 토큰이 일찍 끝났다. 한 번만 새로 받아 다시
                    access = await self._access_token(client, force=True)
                    r = await client.post(url, json=self._payload(token, message),
                                          headers={"Authorization": f"Bearer {access}"})
        except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as e:
            log.warning("fcm send error: %s", type(e).__name__)
            return PushResult(False, error=type(e).__name__[:100])
        if r.status_code == 200:
            return PushResult(True, message_id=str(r.json().get("name", ""))[:200] or None)
        code, dead = _parse_error(r)
        log.info("fcm send failed status=%s code=%s", r.status_code, code)
        return PushResult(False, error=code, invalid_token=dead)


def _parse_error(r: httpx.Response) -> tuple[str, bool]:
    try:
        err = r.json().get("error", {})
    except ValueError:
        return f"HTTP_{r.status_code}", False
    code = err.get("status") or f"HTTP_{r.status_code}"
    token_field_bad = False
    for d in err.get("details", []) or []:
        if str(d.get("@type", "")).endswith("FcmError") and d.get("errorCode"):
            code = d["errorCode"]
        for v in d.get("fieldViolations", []) or []:
            if v.get("field") == "message.token":
                token_field_bad = True
    dead = code in DEAD_TOKEN_CODES or (code == "INVALID_ARGUMENT" and token_field_bad) or r.status_code == 404
    return str(code)[:100], dead
