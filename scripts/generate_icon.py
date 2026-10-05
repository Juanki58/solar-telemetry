"""Generate assets/b-intelligent.ico (+ PNG). Run once when branding the desktop shortcut."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin = max(1, size // 16)
    radius = size // 5
    bg = (14, 90, 92, 255)
    accent = (242, 169, 59, 255)
    leaf = (120, 200, 140, 255)
    white = (245, 248, 247, 255)

    d.rounded_rectangle(
        [margin, margin, size - margin - 1, size - margin - 1],
        radius=radius,
        fill=bg,
    )

    cx, cy = size // 2, size // 2 - size // 18
    r_outer = size * 0.28
    r_inner = size * 0.16
    for i in range(8):
        ang = math.radians(i * 45)
        x1 = cx + r_inner * math.cos(ang)
        y1 = cy + r_inner * math.sin(ang)
        x2 = cx + r_outer * math.cos(ang)
        y2 = cy + r_outer * math.sin(ang)
        w = max(2, size // 18)
        d.line([(x1, y1), (x2, y2)], fill=accent, width=w)

    sun_r = size * 0.14
    d.ellipse([cx - sun_r, cy - sun_r, cx + sun_r, cy + sun_r], fill=accent)

    bw, bh = size * 0.42, size * 0.18
    bx0, by0 = cx - bw / 2, cy + size * 0.18
    d.rounded_rectangle(
        [bx0, by0, bx0 + bw, by0 + bh],
        radius=max(2, size // 28),
        fill=white,
    )
    tip_w, tip_h = size * 0.08, size * 0.08
    d.rectangle(
        [cx - tip_w / 2, by0 - tip_h * 0.55, cx + tip_w / 2, by0],
        fill=white,
    )
    pad = size * 0.04
    fill_w = bw * 0.55
    d.rounded_rectangle(
        [bx0 + pad, by0 + pad, bx0 + pad + fill_w, by0 + bh - pad],
        radius=max(1, size // 40),
        fill=leaf,
    )
    return img


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [make_icon(s) for s in sizes]
    ico_path = ASSETS / "b-intelligent.ico"
    images[-1].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )
    png_path = ASSETS / "b-intelligent.png"
    make_icon(512).save(png_path, format="PNG")
    print(f"Wrote {ico_path} ({ico_path.stat().st_size} bytes)")
    print(f"Wrote {png_path}")


if __name__ == "__main__":
    main()
