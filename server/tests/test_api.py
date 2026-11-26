import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.anthropic import AnthropicProvider
from app.providers.base import ImageInput
from app.providers.fake import fake_result
from app.providers.gemini import GeminiProvider
from app import router

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _fake(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "AUTH_REQUIRED_FOR_ANALYZE"):
        monkeypatch.delenv(k, raising=False)


def test_health():
    assert TestClient(app).get("/health").json() == {"ok": True, "provider": "fake"}


def test_well_known_links_empty_without_secrets(monkeypatch):
    monkeypatch.delenv("ANDROID_CERT_SHA256", raising=False)
    monkeypatch.delenv("APPLE_TEAM_ID", raising=False)
    c = TestClient(app)
    assert c.get("/.well-known/assetlinks.json").json() == []
    body = c.get("/.well-known/apple-app-site-association").json()
    assert body["applinks"]["details"][0]["appID"] == "TEAMID.com.ilgeodeurim.ilgeodeurim"
    assert c.get("/apple-app-site-association").json()["applinks"]["details"][0]["paths"] == ["/f/*"]


@pytest.mark.parametrize("name,typ", [("bill.png", "bill"), ("약봉투.png", "medicine"), ("hospital.png", "hospital")])
def test_analyze_fake(name, typ):
    r = TestClient(app).post("/api/analyze", files=[("images", (name, PNG, "image/png"))])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["docType"] == typ and j["title"] and j["oneLiner"]
    assert j["model"].startswith("fake:")
    if typ == "bill":
        assert j["amount"] == 32400 and len(j["dueDate"]) == 10
        assert j["model"] == "fake:fake-default"
    if typ == "medicine":
        assert j["model"] == "fake:fake-strong"  # 약은 좋은 모델로 올라감


def test_rejects_non_image():
    r = TestClient(app).post("/api/analyze", files=[("images", ("a.txt", b"hello", "text/plain"))])
    assert r.status_code == 415 and "사진" in r.json()["error"]["userMessage"]


def test_too_many():
    files = [("images", (f"{i}.png", PNG, "image/png")) for i in range(6)]
    assert TestClient(app).post("/api/analyze", files=files).status_code == 400


def test_schema_normalizes():
    from app.schema import AnalysisResult
    r = AnalysisResult.model_validate({**fake_result("bill"), "amount": "32,400원", "dueDate": "내일", "docType": "x"})
    assert r.amount == 32400 and r.dueDate is None and r.docType == "other"


def _img():
    return [ImageInput(PNG, "image/png", "x.png")]


def test_gemini_request_and_parse():
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append((req.url.path, req.headers["x-goog-api-key"], body))
        schema = body["generationConfig"]["responseJsonSchema"]
        out = {"docType": "medicine"} if "readable" not in schema["properties"] else fake_result("medicine")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}]})

    p = GeminiProvider("k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    raw, typ, model = asyncio.run(router.run(p, _img()))
    assert typ == "medicine" and model == p.strong_model and raw["docType"] == "medicine"
    assert seen[0][0].endswith(f"{p.classify_model}:generateContent") and seen[0][1] == "k"
    assert seen[1][0].endswith(f"{p.strong_model}:generateContent")
    assert seen[1][2]["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/png"


def test_anthropic_request_and_parse():
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        tool = body["tool_choice"]["name"]
        out = {"docType": "bill"} if tool == "report_type" else fake_result("bill")
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": tool, "input": out}]})

    p = AnthropicProvider("k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    raw, typ, model = asyncio.run(router.run(p, _img()))
    assert typ == "bill" and model == p.default_model and raw["amount"] == 32400
    assert seen[1]["messages"][0]["content"][0]["type"] == "image"
    assert seen[1]["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_fallback_when_strong_model_quota_exceeded():
    calls = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        model = req.url.path.split("/")[-1].split(":")[0]
        calls.append(model)
        if "readable" not in body["generationConfig"]["responseJsonSchema"]["properties"]:
            out = {"docType": "contract"}
        elif model == p.strong_model:
            return httpx.Response(429, json={"error": {"message": "quota"}})
        else:
            out = fake_result("contract")
        assert "temperature" not in body["generationConfig"]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}],
                                         "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}})

    p = GeminiProvider("k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    raw, typ, model = asyncio.run(router.run(p, _img()))
    assert typ == "contract" and model == p.default_model
    assert calls == [p.classify_model, p.strong_model, p.default_model]


def test_bad_request_is_not_retried():
    def handler(req):
        body = json.loads(req.content)
        if "readable" not in body["generationConfig"]["responseJsonSchema"]["properties"]:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"docType":"bill"}'}]}}]})
        return httpx.Response(400, json={"error": {"message": "bad"}})

    p = GeminiProvider("k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(Exception):
        asyncio.run(router.run(p, _img()))


def test_classify_failure_escalates_to_strong_model():
    calls = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        model = req.url.path.split("/")[-1].split(":")[0]
        calls.append(model)
        if "readable" not in body["generationConfig"]["responseJsonSchema"]["properties"]:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(fake_result("medicine"))}]}}]})

    p = GeminiProvider("k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    raw, typ, model = asyncio.run(router.run(p, _img()))
    assert model == p.strong_model and typ == "medicine"
