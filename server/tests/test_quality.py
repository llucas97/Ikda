"""사진 품질 검사: 흐림·어두움·과노출·빈 사진·너무 작음, 그리고 AI 를 부르기 전에 막는지."""
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from app import analysis, quality
from app.main import app as main_app
from app.providers.fake import FakeProvider
from conftest import PNG, doc_image


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("QUALITY_CHECK", "QUALITY_BLUR_MIN", "QUALITY_DARK_MEAN", "QUALITY_MIN_SHORT_SIDE",
              "QUALITY_MIN_LONG_SIDE", "QUALITY_BRIGHT_CLIPPED", "QUALITY_BLANK_CONTENT", "DEBUG_USAGE",
              "AI_PROVIDER", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "AUTH_REQUIRED_FOR_ANALYZE"):
        monkeypatch.delenv(k, raising=False)


class CountingProvider(FakeProvider):
    def __init__(self):
        self.calls = 0

    async def classify(self, images, model):
        self.calls += 1
        return await super().classify(images, model)


@pytest.fixture
def provider(monkeypatch):
    p = CountingProvider()
    monkeypatch.setattr(analysis, "get_provider", lambda: p)
    return p


def _problems(data: bytes) -> list[str]:
    m = quality.measure(data)
    assert m is not None
    return quality.problems(m, quality.Thresholds())


def test_sharp_document_passes():
    m = quality.measure(doc_image())
    assert m.width == 900 and m.height == 1200
    assert m.sharpness > 500 and m.content > 0.3
    assert quality.problems(m, quality.Thresholds()) == []
    assert _problems(doc_image(fmt="PNG")) == []


@pytest.mark.parametrize("kwargs,code", [
    ({"blur": 6}, "photo_blurry"),
    ({"brightness": 0.12}, "photo_dark"),
    ({"w": 300, "h": 400}, "photo_small"),
    ({"color": (255, 255, 255)}, "photo_bright"),
    ({"color": (128, 128, 128)}, "photo_blank"),
])
def test_bad_photos_are_caught(kwargs, code):
    assert code in _problems(doc_image(**kwargs))


def test_mild_blur_still_passes_on_server():
    # 서버는 정말 못 읽는 사진만 막는다 (조금 흐린 것은 앱이 '그래도 보내기'와 함께 묻는다)
    assert _problems(doc_image(blur=1)) == []


def test_undecodable_image_is_skipped_not_rejected():
    assert quality.measure(PNG) is None
    assert quality.first_failure(quality.check([PNG])) is None


def test_multi_page_message_names_the_page():
    results = quality.check([doc_image(), doc_image(blur=6)])
    bad = quality.first_failure(results)
    assert bad.index == 1
    assert quality.user_message(bad, 2).startswith("2번째 사진:")
    assert "흔들렸어요" in quality.user_message(bad, 1)


def test_thresholds_come_from_env(monkeypatch):
    monkeypatch.setenv("QUALITY_BLUR_MIN", "0")
    assert quality.Thresholds.from_env().blur_sharpness == 0
    assert quality.check([doc_image(blur=6)], quality.Thresholds.from_env())[0].problems == []


def _post(*files):
    return TestClient(main_app).post("/api/analyze", files=[("images", f) for f in files])


def test_endpoint_rejects_blurry_before_calling_ai(provider):
    r = _post(("bill.jpg", doc_image(blur=6), "image/jpeg"))
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "photo_blurry" and err["page"] == 1 and err["problems"] == ["photo_blurry"]
    assert "흔들렸어요" in err["userMessage"]
    assert provider.calls == 0  # 돈이 드는 AI 를 부르지 않았다


def test_endpoint_reports_which_page(provider):
    r = _post(("bill1.jpg", doc_image(), "image/jpeg"), ("bill2.jpg", doc_image(brightness=0.1), "image/jpeg"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "photo_dark" and r.json()["error"]["page"] == 2
    assert provider.calls == 0


def test_endpoint_good_photo_reaches_ai_and_debug_has_metrics(provider, monkeypatch):
    monkeypatch.setenv("DEBUG_USAGE", "1")
    r = _post(("bill.jpg", doc_image(), "image/jpeg"))
    assert r.status_code == 200, r.text
    assert provider.calls == 1
    q = r.json()["debug"]["quality"][0]
    assert q["width"] == 900 and q["sharpness"] > 500


def test_quality_check_can_be_turned_off(provider, monkeypatch):
    monkeypatch.setenv("QUALITY_CHECK", "0")
    r = _post(("bill.jpg", doc_image(blur=6), "image/jpeg"))
    assert r.status_code == 200, r.text
    assert provider.calls == 1


def _png_header_only(w: int, h: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b""))


def test_decompression_bomb_is_refused(provider):
    r = _post(("bomb.png", _png_header_only(20000, 20000), "image/png"))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "too_large"
    assert provider.calls == 0
