"""Copy brand PNG into Android mipmap densities as launcher icons."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "b-intelligent.png"
RES = ROOT / "android" / "app" / "src" / "main" / "res"

DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Missing {SRC}; run scripts/generate_icon.py first")
    base = Image.open(SRC).convert("RGBA")
    for folder, size in DENSITIES.items():
        out_dir = RES / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        icon = base.resize((size, size), Image.Resampling.LANCZOS)
        icon.save(out_dir / "ic_launcher.png")
        icon.save(out_dir / "ic_launcher_round.png")
        print(f"Wrote {out_dir} ({size}px)")


if __name__ == "__main__":
    main()
