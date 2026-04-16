#!/usr/bin/env python3
"""
Render every registered effect against random image pairs from assets/.

The assets/ folder is user-provided; it should contain pairs of food photos
(whole dish + sliced/served shots). Two random images per run are picked
without replacement and passed as the top/bottom inputs for dual-image
effects.

Usage:
    python -m scripts.preview_effects                 # 1 pair, both sizes
    python -m scripts.preview_effects --count 4       # 4 random pairs
    python -m scripts.preview_effects --seed 42       # reproducible picks
    python -m scripts.preview_effects --title "Blood Orange Cake" \\
        --subtitle "Bright, zesty, simple to bake"

Outputs land in preview_outputs/<effect>_<size>_<top>__<bottom>_r<n>.jpg
"""
import argparse
import random
import sys
from pathlib import Path

from PIL import Image

from api_functions.effects import list_effects


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def discover_images(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=1, help="Number of random pairs to render (default 1).")
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "preview_outputs",
        help="Output directory.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    parser.add_argument("--title", default="Blood Orange Cake")
    parser.add_argument("--subtitle", default="Bright, zesty, simple to bake")
    parser.add_argument("--brand", default="nomadmouse.com")
    parser.add_argument("--primary", default="", help="Optional primary hex, e.g. '#f4b5c2'. Auto-extracted if empty.")
    parser.add_argument("--secondary", default="", help="Optional secondary (title) hex.")
    parser.add_argument("--tertiary", default="", help="Optional tertiary (subtitle/brand) hex.")
    parser.add_argument("--accent", default="", help="Optional script accent text (used by black_bar_triptych).")
    parser.add_argument("--url", default="", help="Optional URL strip text (used by black_bar_triptych).")
    parser.add_argument(
        "--sizes", nargs="+", default=["pin_2x3", "pin_1x2"],
        help="Output sizes to render (space-separated).",
    )
    parser.add_argument(
        "--only", nargs="*", default=None,
        help="Limit to specific effect names (default: all registered).",
    )
    args = parser.parse_args()

    images = discover_images(ASSETS_DIR)
    if len(images) < 2:
        print(
            f"Need at least 2 images in {ASSETS_DIR}. Found {len(images)}.\n"
            f"Populate the folder with food photo pairs and rerun.",
            file=sys.stderr,
        )
        return 1

    effects = list_effects()
    if args.only:
        effects = [e for e in effects if e.name in set(args.only)]
    if not effects:
        print("No effects to render (registry empty or --only filtered everything).", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    common_kwargs = {
        "title": args.title,
        "subtitle": args.subtitle,
        "brand": args.brand,
        "primary_hex": args.primary or None,
        "secondary_hex": args.secondary or None,
        "tertiary_hex": args.tertiary or None,
    }
    per_effect_extras = {
        "black_bar_triptych": {
            "accent_text": args.accent,
            "url_text": args.url,
        },
    }

    for run in range(args.count):
        top_path, bottom_path = rng.sample(images, 2)
        with Image.open(top_path) as top_src, Image.open(bottom_path) as bot_src:
            top_src.load()
            bot_src.load()

            for effect in effects:
                extras = per_effect_extras.get(effect.name, {})
                for size in args.sizes:
                    if effect.kind == "dual":
                        result = effect.render(
                            image_top=top_src,
                            image_bottom=bot_src,
                            output_size=size,
                            **common_kwargs,
                            **extras,
                        )
                    else:
                        result = effect.render(
                            image=top_src,
                            **common_kwargs,
                            **extras,
                        )

                    out_name = (
                        f"{effect.name}_{size}_"
                        f"{top_path.stem[:24]}__{bottom_path.stem[:24]}_r{run}.jpg"
                    )
                    out_path = args.output / out_name
                    result.save(out_path, format="JPEG", quality=92, optimize=True, progressive=True)
                    print(f"wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
