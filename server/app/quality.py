"""사진 품질 검사. AI 를 부르기 전에 읽을 수 없는 사진을 걸러 돈을 아낀다.

앱(lib/services/photo_quality.dart)도 같은 지표를 같은 방법으로 잰다. 앱은 더 엄격하게 보고
'그래도 보내기'를 허락하고, 서버는 정말 못 읽을 사진만 막는다(기준이 느슨하다).

지표 (긴 변을 1000px 로 줄인 흑백 사진에서):
  sharpness  8x8 칸마다 라플라시안 분산을 재고, 글씨가 있는 칸들의 상위 10% 값. 낮으면 흐림
  mean       평균 밝기 0~255. 낮으면 어두움
  clipped    250 이상(하얗게 날아간) 화소 비율. 높으면 빛 반사·과노출
  content    글씨·무늬가 있는 칸(밝기 표준편차 > 10)의 비율. 거의 0 이면 빈 사진
  edgeSides  가장자리 띠에 글씨가 몰린 변의 수. 서버는 쓰지 않는다 — 여백 없이 꽉 찬 서류 사진도 3~4 가 나온다.
             앱이 스캐너로 잘라 낸 사진에만 '잘렸을 수 있어요' 약한 안내로 쓴다(docs/phase3-plan.md §6)

사진은 메모리에서만 다루고 디스크·로그에 남기지 않는다.
"""
from __future__ import annotations

import io
import logging
import os
from dataclasses import asdict, dataclass

from PIL import Image, ImageFilter, ImageStat

log = logging.getLogger("ilgeodeurim")

WORK_SIDE = 1000
GRID = 8
CONTENT_STD = 10.0
LAPLACIAN = ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)
Image.MAX_IMAGE_PIXELS = 60_000_000  # 압축 폭탄 막기 (60MP 넘으면 DecompressionBombError)


@dataclass(frozen=True)
class Thresholds:
    min_short: int = 400
    min_long: int = 600
    dark_mean: float = 40.0
    bright_clipped: float = 0.95
    bright_content: float = 0.05
    blank_content: float = 0.02
    blur_sharpness: float = 30.0

    @classmethod
    def from_env(cls) -> "Thresholds":
        def f(name: str, default: float) -> float:
            v = os.getenv(name, "").strip()
            return float(v) if v else default

        d = cls()
        return cls(
            min_short=int(f("QUALITY_MIN_SHORT_SIDE", d.min_short)),
            min_long=int(f("QUALITY_MIN_LONG_SIDE", d.min_long)),
            dark_mean=f("QUALITY_DARK_MEAN", d.dark_mean),
            bright_clipped=f("QUALITY_BRIGHT_CLIPPED", d.bright_clipped),
            bright_content=d.bright_content,
            blank_content=f("QUALITY_BLANK_CONTENT", d.blank_content),
            blur_sharpness=f("QUALITY_BLUR_MIN", d.blur_sharpness),
        )


@dataclass(frozen=True)
class Metrics:
    width: int
    height: int
    sharpness: float
    mean: float
    clipped: float
    content: float
    edgeSides: int

    def as_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in asdict(self).items()}


# 문제 코드 → 어르신께 보일 말. 앱은 code 로 그림을 고른다.
MESSAGES = {
    "photo_small": "사진이 너무 작아요. 서류에 조금 더 가까이 대고 다시 찍어 주세요.",
    "photo_dark": "사진이 너무 어두워요. 불을 켜거나 밝은 곳에서 다시 찍어 주세요.",
    "photo_bright": "빛이 반사돼서 글씨가 안 보여요. 형광등 바로 아래를 피해서 다시 찍어 주세요.",
    "photo_blank": "서류가 잘 안 보여요. 서류 전체가 화면에 나오게 다시 찍어 주세요.",
    "photo_blurry": "사진이 흔들렸어요. 휴대폰을 꼭 잡고 다시 찍어 주세요.",
}


def enabled() -> bool:
    return os.getenv("QUALITY_CHECK", "1") != "0"


def measure(data: bytes) -> Metrics | None:
    """사진을 열 수 없으면(HEIC 처럼 Pillow 가 모르는 형식, 깨진 파일) None — 검사를 건너뛴다."""
    try:
        img = Image.open(io.BytesIO(data))
        width, height = img.size
        if img.format == "JPEG":
            img.draft("L", (WORK_SIDE, WORK_SIDE))  # JPEG 는 작게 풀어서 빠르다
        img = img.convert("L")
    except Image.DecompressionBombError:
        raise
    except Exception:
        return None
    scale = WORK_SIDE / max(img.size)
    if scale < 1:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.Resampling.BILINEAR)

    hist = img.histogram()
    total = sum(hist) or 1
    mean = sum(i * n for i, n in enumerate(hist)) / total
    clipped = sum(hist[250:]) / total

    # Pillow 의 Kernel 은 가장자리 1px 을 거르지 않고 원래 값을 둔다. 그 줄이 '선명함'으로 잡히지 않게 잘라 낸다.
    w, h = img.size
    if w > 8 and h > 8:
        img = img.crop((2, 2, w - 2, h - 2))
    lap = img.filter(LAPLACIAN).crop((1, 1, img.width - 1, img.height - 1))
    img = img.crop((1, 1, img.width - 1, img.height - 1))
    w, h = img.size
    tile_std: list[list[float]] = []
    sharp: list[float] = []
    for gy in range(GRID):
        row = []
        for gx in range(GRID):
            box = (gx * w // GRID, gy * h // GRID, (gx + 1) * w // GRID, (gy + 1) * h // GRID)
            if box[2] <= box[0] or box[3] <= box[1]:
                row.append(0.0)
                continue
            std = ImageStat.Stat(img.crop(box)).stddev[0]
            row.append(std)
            if std > CONTENT_STD:
                sharp.append(ImageStat.Stat(lap.crop(box)).var[0])
        tile_std.append(row)
    content = len(sharp) / (GRID * GRID)
    sharp.sort()
    sharpness = sharp[int(len(sharp) * 0.9)] if len(sharp) > 1 else (sharp[0] if sharp else 0.0)

    # 가장자리 칸에 글씨가 몰려 있으면 서류가 잘렸을 수 있다 (한 변의 칸 대부분이 글씨).
    sides = [tile_std[0], tile_std[-1], [r[0] for r in tile_std], [r[-1] for r in tile_std]]
    edge_sides = sum(1 for s in sides if sum(1 for v in s if v > CONTENT_STD * 2) >= GRID * 0.75)
    return Metrics(width, height, sharpness, mean, clipped, content, edge_sides)


def problems(m: Metrics, t: Thresholds) -> list[str]:
    """서버가 막는 문제. 앞에 올수록 먼저 고칠 것."""
    out: list[str] = []
    if min(m.width, m.height) < t.min_short or max(m.width, m.height) < t.min_long:
        out.append("photo_small")
    if m.mean < t.dark_mean:
        out.append("photo_dark")
    elif m.clipped > t.bright_clipped and m.content < t.bright_content:
        out.append("photo_bright")
    elif m.content < t.blank_content:
        out.append("photo_blank")
    elif m.sharpness < t.blur_sharpness:
        out.append("photo_blurry")
    return out


@dataclass(frozen=True)
class PageResult:
    index: int  # 0부터
    metrics: Metrics | None
    problems: list[str]


def check(pages: list[bytes], t: Thresholds | None = None) -> list[PageResult]:
    t = t or Thresholds.from_env()
    results = []
    for i, data in enumerate(pages):
        m = measure(data)
        results.append(PageResult(i, m, problems(m, t) if m else []))
    return results


def first_failure(results: list[PageResult]) -> PageResult | None:
    return next((r for r in results if r.problems), None)


def user_message(failure: PageResult, total_pages: int) -> str:
    msg = MESSAGES[failure.problems[0]]
    return f"{failure.index + 1}번째 사진: {msg}" if total_pages > 1 else msg
