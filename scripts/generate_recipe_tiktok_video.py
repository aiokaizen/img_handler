#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import Sequence

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

try:
    from .generate_tiktok_video import (
        FRAME_HEIGHT,
        FRAME_WIDTH,
        DEFAULT_SUBTITLE_FONT,
        ease_in_out,
        ease_out_back,
        ease_out_cubic,
        load_font,
        measure_block,
        title_from_stem,
        wrap_text,
    )
except ImportError:
    from generate_tiktok_video import (
        FRAME_HEIGHT,
        FRAME_WIDTH,
        DEFAULT_SUBTITLE_FONT,
        ease_in_out,
        ease_out_back,
        ease_out_cubic,
        load_font,
        measure_block,
        title_from_stem,
        wrap_text,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a 60-second TikTok recipe video with title and ingredients phases."
    )
    parser.add_argument("image", type=Path, help="Input image path")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output MP4 path. Defaults to videos/<image-stem>_recipe_tiktok.mp4",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Title text. Defaults to a titleized version of the input filename.",
    )
    parser.add_argument("--subtitle", default="", help="Optional subtitle text for the intro segment")
    parser.add_argument(
        "--ingredient",
        action="append",
        default=[],
        help="Ingredient line. Repeat this flag for multiple ingredients.",
    )
    parser.add_argument(
        "--ingredients-file",
        type=Path,
        default=None,
        help="Optional text file with one ingredient per line.",
    )
    parser.add_argument("--ingredients-title", default="Ingredients", help="Heading for the ingredients card")
    parser.add_argument("--brand", default="", help="Optional small bottom-right brand text")
    parser.add_argument("--title-duration", type=float, default=10.0, help="Intro segment duration in seconds")
    parser.add_argument(
        "--ingredients-duration",
        type=float,
        default=50.0,
        help="Ingredients segment duration in seconds",
    )
    parser.add_argument(
        "--transition",
        choices=("fade", "slide_up", "wipe_left", "zoom_cross", "blur_fade"),
        default="fade",
        help="Transition effect between intro and ingredients phases",
    )
    parser.add_argument(
        "--transition-duration",
        type=float,
        default=1.0,
        help="Transition duration in seconds. Counts inside the ingredients phase.",
    )
    parser.add_argument("--fps", type=int, default=30, help="Frames per second")
    parser.add_argument("--zoom-peak", type=float, default=1.08, help="Peak zoom multiplier at the segment boundary")
    return parser.parse_args()


def load_ingredients(args: argparse.Namespace) -> list[str]:
    ingredients = list(args.ingredient)

    if args.ingredients_file:
        lines = args.ingredients_file.expanduser().read_text(encoding="utf-8").splitlines()
        ingredients.extend(line.strip() for line in lines if line.strip())

    ingredients = [item.strip() for item in ingredients if item.strip()]
    if not ingredients:
        raise SystemExit("Provide at least one ingredient via --ingredient or --ingredients-file.")

    return ingredients


def fit_title_card(title: str, subtitle: str) -> dict[str, object]:
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    pad_x = 74
    pad_y = 58
    max_text_width = FRAME_WIDTH - 220
    title_size = 96
    subtitle_size = 52
    title_spacing = 10
    subtitle_spacing = 8
    gap = 24

    fitted = None
    for _ in range(20):
        title_font = load_font("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", title_size)
        subtitle_font = load_font(DEFAULT_SUBTITLE_FONT, subtitle_size)
        title_lines = wrap_text(measure, title, title_font, max_text_width)
        subtitle_lines = wrap_text(measure, subtitle, subtitle_font, max_text_width)
        title_width, title_height, title_line_height = measure_block(measure, title_lines, title_font, title_spacing)
        subtitle_width, subtitle_height, subtitle_line_height = measure_block(
            measure, subtitle_lines, subtitle_font, subtitle_spacing
        )

        box_width = min(FRAME_WIDTH - 120, max(title_width, subtitle_width, 1) + pad_x * 2)
        body_gap = gap if subtitle_lines else 0
        box_height = title_height + subtitle_height + body_gap + pad_y * 2

        fitted = {
            "title_font": title_font,
            "subtitle_font": subtitle_font,
            "title_lines": title_lines,
            "subtitle_lines": subtitle_lines,
            "title_line_height": title_line_height,
            "subtitle_line_height": subtitle_line_height,
            "title_spacing": title_spacing,
            "subtitle_spacing": subtitle_spacing,
            "gap": body_gap,
            "box_width": box_width,
            "box_height": box_height,
            "pad_x": pad_x,
            "pad_y": pad_y,
            "text_width": box_width - pad_x * 2,
        }

        if box_height <= 520 and len(title_lines) <= 4 and len(subtitle_lines) <= 3:
            return fitted

        title_size = max(58, int(title_size * 0.92))
        subtitle_size = max(32, int(subtitle_size * 0.92))
        title_spacing = max(6, int(title_spacing * 0.92))
        subtitle_spacing = max(4, int(subtitle_spacing * 0.92))
        gap = max(14, int(gap * 0.92))

    return fitted if fitted is not None else {}


def fit_ingredients_card(heading: str, ingredients: list[str]) -> dict[str, object]:
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    pad_x = 74
    pad_y = 56
    max_text_width = FRAME_WIDTH - 220
    heading_size = 78
    item_size = 44
    heading_spacing = 10
    item_spacing = 12
    gap = 28

    fitted = None
    for _ in range(24):
        heading_font = load_font("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", heading_size)
        item_font = load_font(DEFAULT_SUBTITLE_FONT, item_size)
        heading_lines = wrap_text(measure, heading, heading_font, max_text_width)

        ingredient_lines: list[str] = []
        for ingredient in ingredients:
            wrapped = wrap_text(measure, f"- {ingredient}", item_font, max_text_width)
            ingredient_lines.extend(wrapped or [f"- {ingredient}"])

        heading_width, heading_height, heading_line_height = measure_block(
            measure, heading_lines, heading_font, heading_spacing
        )
        items_width, items_height, item_line_height = measure_block(measure, ingredient_lines, item_font, item_spacing)

        box_width = min(FRAME_WIDTH - 120, max(heading_width, items_width, 1) + pad_x * 2)
        box_height = heading_height + items_height + gap + pad_y * 2

        fitted = {
            "heading_font": heading_font,
            "item_font": item_font,
            "heading_lines": heading_lines,
            "ingredient_lines": ingredient_lines,
            "heading_line_height": heading_line_height,
            "item_line_height": item_line_height,
            "heading_spacing": heading_spacing,
            "item_spacing": item_spacing,
            "gap": gap,
            "box_width": box_width,
            "box_height": box_height,
            "pad_x": pad_x,
            "pad_y": pad_y,
            "text_width": box_width - pad_x * 2,
        }

        if box_height <= 1040 and len(ingredient_lines) <= 12:
            return fitted

        heading_size = max(46, int(heading_size * 0.92))
        item_size = max(30, int(item_size * 0.92))
        heading_spacing = max(6, int(heading_spacing * 0.92))
        item_spacing = max(8, int(item_spacing * 0.92))
        gap = max(18, int(gap * 0.92))

    return fitted if fitted is not None else {}


def render_camera_frame(image: Image.Image, zoom: float, pan_x: float, pan_y: float) -> Image.Image:
    base_scale = max(FRAME_WIDTH / image.width, FRAME_HEIGHT / image.height)
    source_width = FRAME_WIDTH / base_scale / zoom
    source_height = FRAME_HEIGHT / base_scale / zoom

    spare_x = max(0.0, image.width - source_width)
    spare_y = max(0.0, image.height - source_height)
    center_x = image.width / 2.0 + spare_x * pan_x
    center_y = image.height * 0.46 + spare_y * pan_y

    center_x = min(max(source_width / 2.0, center_x), image.width - source_width / 2.0)
    center_y = min(max(source_height / 2.0, center_y), image.height - source_height / 2.0)

    left = center_x - source_width / 2.0
    top = center_y - source_height / 2.0
    right = center_x + source_width / 2.0
    bottom = center_y + source_height / 2.0

    return image.transform(
        (FRAME_WIDTH, FRAME_HEIGHT),
        Image.Transform.EXTENT,
        (left, top, right, bottom),
        resample=Image.Resampling.BICUBIC,
    )


def render_title_segment_frame(
    image: Image.Image,
    title_spec: dict[str, object],
    progress: float,
    zoom_peak: float,
    brand: str,
) -> Image.Image:
    zoom = 1.0 + (zoom_peak - 1.0) * ease_in_out(progress)
    pan_x = 0.10 * ease_in_out(progress)
    pan_y = -0.05 * ease_in_out(progress)
    frame = render_camera_frame(image, zoom, pan_x, pan_y).convert("RGBA")

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    card_intro = ease_out_back(progress)
    title_intro = ease_out_back(min(1.0, progress * 1.15), overshoot=1.0)
    subtitle_intro = ease_out_cubic(max(0.0, min(1.0, (progress - 0.14) / 0.86)))

    box_width = int(title_spec["box_width"])
    box_height = int(title_spec["box_height"])
    pad_x = int(title_spec["pad_x"])
    pad_y = int(title_spec["pad_y"])
    text_width = int(title_spec["text_width"])

    box_left = (FRAME_WIDTH - box_width) // 2
    box_top = int(FRAME_HEIGHT * 0.66 + (1.0 - card_intro) * 44)
    box_right = box_left + box_width
    box_bottom = box_top + box_height
    radius = 34

    card_alpha = int(220 * max(0.0, min(1.0, card_intro)))
    shadow_alpha = int(58 * max(0.0, min(1.0, card_intro)))
    draw.rounded_rectangle(
        (box_left, box_top + 12, box_right, box_bottom + 12),
        radius=radius,
        fill=(48, 36, 28, shadow_alpha),
    )
    draw.rounded_rectangle(
        (box_left, box_top, box_right, box_bottom),
        radius=radius,
        fill=(249, 244, 238, card_alpha),
        outline=(135, 109, 88, min(48, card_alpha)),
        width=2,
    )

    content_x = box_left + pad_x
    y = box_top + pad_y
    title_font = title_spec["title_font"]
    subtitle_font = title_spec["subtitle_font"]
    title_lines = title_spec["title_lines"]
    subtitle_lines = title_spec["subtitle_lines"]
    title_line_height = int(title_spec["title_line_height"])
    subtitle_line_height = int(title_spec["subtitle_line_height"])
    title_spacing = int(title_spec["title_spacing"])
    subtitle_spacing = int(title_spec["subtitle_spacing"])
    gap = int(title_spec["gap"])
    title_offset = int((1.0 - title_intro) * 22)
    subtitle_offset = int((1.0 - subtitle_intro) * 16)

    for line in title_lines:
        line_width = draw.textbbox((0, 0), line, font=title_font, stroke_width=2)[2]
        x = content_x + (text_width - line_width) // 2
        title_alpha = int(255 * max(0.0, min(1.0, title_intro)))
        draw.text(
            (x, y + 2 + title_offset),
            line,
            font=title_font,
            fill=(255, 255, 255, min(120, title_alpha)),
            stroke_width=2,
            stroke_fill=(255, 255, 255, min(120, title_alpha)),
        )
        draw.text(
            (x, y + title_offset),
            line,
            font=title_font,
            fill=(64, 44, 32, title_alpha),
            stroke_width=2,
            stroke_fill=(64, 44, 32, title_alpha),
        )
        y += title_line_height + title_spacing

    if subtitle_lines:
        y += gap
        subtitle_alpha = int(255 * max(0.0, min(1.0, subtitle_intro)))
        for line in subtitle_lines:
            line_width = draw.textbbox((0, 0), line, font=subtitle_font)[2]
            x = content_x + (text_width - line_width) // 2
            draw.text((x, y + 2 + subtitle_offset), line, font=subtitle_font, fill=(255, 255, 255, min(96, subtitle_alpha)))
            draw.text((x, y + subtitle_offset), line, font=subtitle_font, fill=(98, 76, 62, subtitle_alpha))
            y += subtitle_line_height + subtitle_spacing

    if brand:
        brand_alpha = int(200 * ease_out_cubic(max(0.0, min(1.0, (progress - 0.12) / 0.88))))
        brand_font = load_font(DEFAULT_SUBTITLE_FONT, 30)
        brand_bbox = draw.textbbox((0, 0), brand, font=brand_font)
        brand_x = FRAME_WIDTH - 42 - (brand_bbox[2] - brand_bbox[0])
        brand_y = FRAME_HEIGHT - 58 - (brand_bbox[3] - brand_bbox[1])
        draw.text((brand_x, brand_y), brand, font=brand_font, fill=(244, 239, 234, brand_alpha))

    return Image.alpha_composite(frame, overlay).convert("RGB")


def render_ingredients_segment_frame(
    image: Image.Image,
    ingredients_spec: dict[str, object],
    progress: float,
    zoom_peak: float,
    brand: str,
) -> Image.Image:
    zoom = zoom_peak - (zoom_peak - 1.0) * ease_in_out(progress)
    pan_x = 0.10 * (1.0 - ease_in_out(progress))
    pan_y = -0.05 + 0.08 * ease_in_out(progress)
    frame = render_camera_frame(image, zoom, pan_x, pan_y).convert("RGBA")

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    box_width = int(ingredients_spec["box_width"])
    box_height = int(ingredients_spec["box_height"])
    pad_x = int(ingredients_spec["pad_x"])
    pad_y = int(ingredients_spec["pad_y"])
    text_width = int(ingredients_spec["text_width"])
    box_left = (FRAME_WIDTH - box_width) // 2
    box_top = int(FRAME_HEIGHT * 0.38)
    box_right = box_left + box_width
    box_bottom = box_top + box_height
    radius = 36

    draw.rounded_rectangle(
        (box_left, box_top + 14, box_right, box_bottom + 14),
        radius=radius,
        fill=(44, 33, 27, 56),
    )
    draw.rounded_rectangle(
        (box_left, box_top, box_right, box_bottom),
        radius=radius,
        fill=(249, 244, 238, 228),
        outline=(135, 109, 88, 52),
        width=2,
    )

    content_x = box_left + pad_x
    y = box_top + pad_y
    heading_font = ingredients_spec["heading_font"]
    item_font = ingredients_spec["item_font"]
    heading_lines = ingredients_spec["heading_lines"]
    ingredient_lines = ingredients_spec["ingredient_lines"]
    heading_line_height = int(ingredients_spec["heading_line_height"])
    item_line_height = int(ingredients_spec["item_line_height"])
    heading_spacing = int(ingredients_spec["heading_spacing"])
    item_spacing = int(ingredients_spec["item_spacing"])
    gap = int(ingredients_spec["gap"])

    heading_alpha = 255
    item_alpha = 255
    for line in heading_lines:
        line_width = draw.textbbox((0, 0), line, font=heading_font, stroke_width=2)[2]
        x = content_x + (text_width - line_width) // 2
        draw.text(
            (x, y + 2),
            line,
            font=heading_font,
            fill=(255, 255, 255, 110),
            stroke_width=2,
            stroke_fill=(255, 255, 255, 110),
        )
        draw.text(
            (x, y),
            line,
            font=heading_font,
            fill=(64, 44, 32, heading_alpha),
            stroke_width=2,
            stroke_fill=(64, 44, 32, heading_alpha),
        )
        y += heading_line_height + heading_spacing

    divider_y = y + 8
    divider_margin = max(60, int(box_width * 0.22))
    draw.line(
        (box_left + divider_margin, divider_y, box_right - divider_margin, divider_y),
        fill=(173, 139, 111, 115),
        width=3,
    )
    y += gap

    for line in ingredient_lines:
        draw.text((content_x, y + 2), line, font=item_font, fill=(255, 255, 255, 84))
        draw.text((content_x, y), line, font=item_font, fill=(92, 72, 60, item_alpha))
        y += item_line_height + item_spacing

    if brand:
        brand_font = load_font(DEFAULT_SUBTITLE_FONT, 30)
        brand_bbox = draw.textbbox((0, 0), brand, font=brand_font)
        brand_x = FRAME_WIDTH - 42 - (brand_bbox[2] - brand_bbox[0])
        brand_y = FRAME_HEIGHT - 58 - (brand_bbox[3] - brand_bbox[1])
        draw.text((brand_x, brand_y), brand, font=brand_font, fill=(244, 239, 234, 190))

    return Image.alpha_composite(frame, overlay).convert("RGB")


def transition_fade(frame_a: Image.Image, frame_b: Image.Image, progress: float) -> Image.Image:
    return Image.blend(frame_a, frame_b, progress)


def transition_slide_up(frame_a: Image.Image, frame_b: Image.Image, progress: float) -> Image.Image:
    result = frame_a.copy()
    offset = int((1.0 - progress) * FRAME_HEIGHT)
    result.paste(frame_b, (0, offset - FRAME_HEIGHT))
    return result


def transition_wipe_left(frame_a: Image.Image, frame_b: Image.Image, progress: float) -> Image.Image:
    result = frame_a.copy()
    wipe_width = int(FRAME_WIDTH * progress)
    if wipe_width > 0:
        crop = frame_b.crop((FRAME_WIDTH - wipe_width, 0, FRAME_WIDTH, FRAME_HEIGHT))
        result.paste(crop, (FRAME_WIDTH - wipe_width, 0))
    return result


def transition_zoom_cross(frame_a: Image.Image, frame_b: Image.Image, progress: float) -> Image.Image:
    result = frame_a.copy()
    scale = 1.06 - 0.06 * progress
    resized = frame_b.resize(
        (int(FRAME_WIDTH * scale), int(FRAME_HEIGHT * scale)),
        Image.Resampling.BICUBIC,
    )
    left = (resized.width - FRAME_WIDTH) // 2
    top = (resized.height - FRAME_HEIGHT) // 2
    resized = resized.crop((left, top, left + FRAME_WIDTH, top + FRAME_HEIGHT))
    return Image.blend(result, resized, progress)


def transition_blur_fade(frame_a: Image.Image, frame_b: Image.Image, progress: float) -> Image.Image:
    blurred = frame_a.filter(ImageFilter.GaussianBlur(radius=progress * 10.0))
    return Image.blend(blurred, frame_b, progress)


TRANSITIONS = {
    "fade": transition_fade,
    "slide_up": transition_slide_up,
    "wipe_left": transition_wipe_left,
    "zoom_cross": transition_zoom_cross,
    "blur_fade": transition_blur_fade,
}

VALID_TRANSITIONS = tuple(TRANSITIONS.keys())


def generate_recipe_video(
    image: Image.Image,
    *,
    output_path: Path,
    title: str,
    subtitle: str = "",
    ingredients: Sequence[str],
    ingredients_title: str = "Ingredients",
    brand: str = "",
    title_duration: float = 10.0,
    ingredients_duration: float = 50.0,
    transition: str = "fade",
    transition_duration: float = 1.0,
    fps: int = 30,
    zoom_peak: float = 1.08,
) -> Path:
    if not ingredients:
        raise ValueError("At least one ingredient is required")
    if transition not in TRANSITIONS:
        raise ValueError(f"Unsupported transition '{transition}'")
    if title_duration <= 0 or ingredients_duration <= 0:
        raise ValueError("Durations must be greater than zero")
    if transition_duration <= 0:
        raise ValueError("Transition duration must be greater than zero")
    if fps <= 0:
        raise ValueError("FPS must be greater than zero")
    if zoom_peak < 1.0:
        raise ValueError("zoom_peak must be at least 1.0")

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_image = ImageOps.exif_transpose(image).convert("RGB")
    clean_ingredients = [item.strip() for item in ingredients if item.strip()]
    if not clean_ingredients:
        raise ValueError("At least one non-empty ingredient is required")

    title_spec = fit_title_card(title, subtitle)
    ingredients_spec = fit_ingredients_card(ingredients_title, clean_ingredients)

    title_frames = max(1, int(title_duration * fps))
    ingredients_frames = max(1, int(ingredients_duration * fps))
    transition_frames = min(ingredients_frames, max(1, int(transition_duration * fps)))
    total_frames = title_frames + ingredients_frames
    transition_fn = TRANSITIONS[transition]

    writer = imageio.get_writer(
        output_path,
        fps=fps,
        codec="libx264",
        ffmpeg_log_level="error",
        macro_block_size=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )

    try:
        for frame_index in range(total_frames):
            if frame_index < title_frames:
                title_progress = frame_index / max(1, title_frames - 1)
                frame = render_title_segment_frame(
                    base_image,
                    title_spec,
                    title_progress,
                    zoom_peak,
                    brand,
                )
            else:
                ingredient_index = frame_index - title_frames
                ingredient_progress = ingredient_index / max(1, ingredients_frames - 1)
                ingredient_frame = render_ingredients_segment_frame(
                    base_image,
                    ingredients_spec,
                    ingredient_progress,
                    zoom_peak,
                    brand,
                )

                if ingredient_index < transition_frames:
                    transition_progress = ingredient_index / max(1, transition_frames - 1)
                    title_frame = render_title_segment_frame(
                        base_image,
                        title_spec,
                        1.0,
                        zoom_peak,
                        brand,
                    )
                    frame = transition_fn(title_frame, ingredient_frame, transition_progress)
                else:
                    frame = ingredient_frame

            writer.append_data(np.asarray(frame))
    finally:
        writer.close()

    return output_path


def main() -> None:
    args = parse_args()
    image_path = args.image.expanduser().resolve()
    if not image_path.exists():
        raise SystemExit(f"Input image not found: {image_path}")

    ingredients = load_ingredients(args)
    title = args.title or title_from_stem(image_path.stem)
    output_path = args.output or Path("videos") / f"{image_path.stem}_recipe_tiktok.mp4"
    generated_path = generate_recipe_video(
        Image.open(image_path),
        output_path=output_path,
        title=title,
        subtitle=args.subtitle,
        ingredients=ingredients,
        ingredients_title=args.ingredients_title,
        brand=args.brand,
        title_duration=args.title_duration,
        ingredients_duration=args.ingredients_duration,
        transition=args.transition,
        transition_duration=args.transition_duration,
        fps=args.fps,
        zoom_peak=args.zoom_peak,
    )

    print(generated_path)


if __name__ == "__main__":
    main()
