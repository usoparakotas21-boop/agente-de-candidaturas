"""Render Chrome Web Store PNG icons matching app/static/favicon.svg."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "chrome-extension" / "icons"
SCALE = 8
BASE = 64 * SCALE


def render_icon() -> Image.Image:
    image = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def n(value: float) -> int:
        return round(value * SCALE)

    draw.rounded_rectangle((n(1), n(1), n(63), n(63)), radius=n(18), fill="#174578")
    draw.arc((n(12), n(12), n(52), n(52)), start=50, end=310, fill="#ffffff", width=n(9))
    draw.ellipse((n(35), n(34), n(57), n(56)), fill="#53e0bc", outline="#174578", width=n(3))
    draw.line(
        ((n(41.5), n(44.8)), (n(44.7), n(48.0)), (n(50.9), n(41.5))),
        fill="#103456",
        width=n(3.2),
        joint="curve",
    )
    return image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    master = render_icon()
    for size in (16, 32, 48, 128):
        resized = master.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(OUT / f"icon{size}.png", format="PNG", optimize=True)
    print("Ícones do Copiloto gerados: 16, 32, 48 e 128 px")


if __name__ == "__main__":
    main()
