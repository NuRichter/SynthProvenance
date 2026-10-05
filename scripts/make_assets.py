"""Generate the application icon and logo (deterministic, no external files)."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def icon(size: int = 256) -> Image.Image:
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.18), fill=(14, 19, 24, 255), outline=(36, 49, 64, 255), width=max(1, s // 64))
    c, r = s / 2, s * 0.34
    d.ellipse((c - r, c - r, c + r, c + r), outline=(76, 195, 217, 255), width=max(2, s // 22))
    for i, (w, col) in enumerate(((0.56, (76, 195, 217, 255)), (0.40, (61, 127, 217, 255)), (0.24, (70, 179, 123, 255)))):
        y = c - s * 0.10 + i * s * 0.10
        d.rounded_rectangle((c - s * w / 2, y - s * 0.025, c + s * w / 2, y + s * 0.025), radius=s * 0.02, fill=col)
    return im


def main() -> None:
    a = ROOT / "assets"
    a.mkdir(exist_ok=True)
    big = icon(256)
    big.save(a / "icon.png")
    big.save(a / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    logo = Image.new("RGBA", (720, 160), (14, 19, 24, 255))
    logo.paste(icon(128), (16, 16), icon(128))
    d = ImageDraw.Draw(logo)
    d.text((170, 40), "SynthProvenance", fill=(213, 222, 231, 255), font_size=44) if hasattr(d, "text") else None
    d.text((172, 100), "Insyide Innovations x NuRichter Workspace", fill=(125, 140, 155, 255), font_size=20)
    logo.save(a / "logo.png")
    print("assets written")


if __name__ == "__main__":
    main()
