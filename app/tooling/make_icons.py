"""읽다 아이콘을 Android·iOS·웹 크기로 만든다. Flutter 가 없는 PC용.

원본: 저장소 루트 .agent/ikda_icon.png
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".agent" / "ikda_icon.png"
APP = ROOT / "app"
PAPER = (255, 253, 248, 255)

ANDROID = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}
FOREGROUND = {
    "mipmap-mdpi": 108,
    "mipmap-hdpi": 162,
    "mipmap-xhdpi": 216,
    "mipmap-xxhdpi": 324,
    "mipmap-xxxhdpi": 432,
}


def fit(src: Image.Image, size: int, inset: float = 1.0) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), PAPER)
    inner = max(1, int(size * inset))
    icon = src.resize((inner, inner), Image.Resampling.LANCZOS)
    canvas.paste(icon, ((size - inner) // 2, (size - inner) // 2), icon)
    return canvas


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    brand = APP / "assets" / "brand"
    brand.mkdir(parents=True, exist_ok=True)
    src.save(brand / "app_icon.png")

    res = APP / "android" / "app" / "src" / "main" / "res"
    for folder, size in ANDROID.items():
        out = res / folder
        out.mkdir(parents=True, exist_ok=True)
        fit(src, size).save(out / "ic_launcher.png")
    for folder, size in FOREGROUND.items():
        out = res / folder
        out.mkdir(parents=True, exist_ok=True)
        fit(src, size, inset=0.72).save(out / "ic_launcher_foreground.png")

    ios = APP / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
    ios.mkdir(parents=True, exist_ok=True)
    catalog = ios / "Contents.json"
    names = []
    if catalog.exists():
        import json
        names = [img["filename"] for img in json.loads(catalog.read_text(encoding="utf-8"))["images"] if "filename" in img]
    for name in names:
        # Icon-App-20x20@2x.png / Icon-App-83.5x83.5@2x.png / Icon-App-1024x1024@1x.png
        stem = name.replace("Icon-App-", "").replace(".png", "")
        point, scale = stem.split("@")
        px = int(round(float(point.split("x")[0]) * int(scale[0])))
        image = fit(src, px)
        if px == 1024:
            rgb = Image.new("RGB", (px, px), PAPER[:3])
            rgb.paste(image, mask=image.getchannel("A"))
            rgb.save(ios / name, format="PNG")
        else:
            image.save(ios / name)

    web = APP / "web"
    icons = web / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    for size, name in ((192, "Icon-192.png"), (512, "Icon-512.png")):
        fit(src, size).save(icons / name)
        fit(src, size, inset=0.72).save(icons / name.replace("Icon-", "Icon-maskable-"))
    fit(src, 32).save(web / "favicon.png")
    print("icons written")


if __name__ == "__main__":
    main()
