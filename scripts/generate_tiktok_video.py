#!/usr/bin/env python3
import argparse
import math
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

DEFAULT_TITLE_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
DEFAULT_SUBTITLE_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a simple TikTok-style zoom video from a single image."
    )
    parser.add_argument("image", type=Path, help="Input image path")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output MP4 path. Defaults to videos/<image-stem>_tiktok.mp4",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Title text. Defaults to a titleized version of the input filename.",
    )
    parser.add_argument("--subtitle", default="", help="Optional subtitle text")
    parser.add_argument("--brand", default="", help="Optional small bottom-right brand text")
    parser.add_argument("--duration", type=float, default=10.0, help="Duration in seconds")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second")
    parser.add_argument("--zoom-end", type=float, default=1.08, help="Final zoom multiplier")
    parser.add_argument(
        "--motion",
        choices=("push_in", "bounce"),
        default="bounce",
        help="Camera motion style. 'bounce' zooms in and then back out with eased motion.",
    )
    return parser.parse_args()


def title_from_stem(stem: str) -> str:
    return " ".join(part.capitalize() for part in stem.replace("-", " ").replace("_", " ").split())


def load_font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = (text or "").strip().split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def measure_block(draw: ImageDraw.ImageDraw, lines: list[str], font: ImageFont.ImageFont, spacing: int) -> tuple[int, int, int]:
    if not lines:
        return 0, 0, 0
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_height = bbox[3] - bbox[1]
    width = max(draw.textbbox((0, 0), line, font=font)[2] for line in lines)
    height = len(lines) * line_height + max(0, len(lines) - 1) * spacing
    return width, height, line_height


def ease_in_out(progress: float) -> float:
    progress = max(0.0, min(1.0, progress))
    return 0.5 - 0.5 * math.cos(progress * math.pi)


def ease_out_cubic(progress: float) -> float:
    progress = max(0.0, min(1.0, progress))
    return 1.0 - (1.0 - progress) ** 3


def ease_out_back(progress: float, overshoot: float = 1.2) -> float:
    progress = max(0.0, min(1.0, progress))
    value = 1.0 + (overshoot + 1.0) * (progress - 1.0) ** 3 + overshoot * (progress - 1.0) ** 2
    return value


def fade_progress(time_s: float, start: float, duration: float) -> float:
    if duration <= 0:
        return 1.0
    return max(0.0, min(1.0, (time_s - start) / duration))


def get_motion_zoom(progress: float, zoom_end: float, motion: str) -> float:
    if motion == "bounce":
        curve = 0.5 - 0.5 * math.cos(progress * 2.0 * math.pi)
    else:
        curve = ease_in_out(progress)
    return 1.0 + (zoom_end - 1.0) * curve


def get_motion_emphasis(progress: float, motion: str) -> float:
    if motion == "bounce":
        return math.sin(progress * math.pi)
    return ease_in_out(progress)


def render_cover_frame(image: Image.Image, progress: float, zoom_end: float, motion: str) -> Image.Image:
    zoom = get_motion_zoom(progress, zoom_end, motion)
    base_scale = max(FRAME_WIDTH / image.width, FRAME_HEIGHT / image.height)

    source_width = FRAME_WIDTH / base_scale / zoom
    source_height = FRAME_HEIGHT / base_scale / zoom

    spare_x = max(0.0, image.width - source_width)
    spare_y = max(0.0, image.height - source_height)
    emphasis = get_motion_emphasis(progress, motion)

    if motion == "bounce":
        center_x = image.width / 2.0 + spare_x * 0.18 * emphasis
        center_y = image.height * 0.46 - spare_y * 0.08 * emphasis
    else:
        drift = ease_in_out(progress)
        center_x = image.width / 2.0 + spare_x * 0.14 * drift
        center_y = image.height * 0.46 - spare_y * 0.05 * drift

    center_x = min(max(source_width / 2.0, center_x), image.width - source_width / 2.0)
    center_y = min(max(source_height / 2.0, center_y), image.height - source_height / 2.0)

    left = center_x - source_width / 2.0
    top = center_y - source_height / 2.0
    right = center_x + source_width / 2.0
    bottom = center_y + source_height / 2.0

    if left < 0:
        right -= left
        left = 0.0
    if right > image.width:
        left -= right - image.width
        right = float(image.width)
    if top < 0:
        bottom -= top
        top = 0.0
    if bottom > image.height:
        top -= bottom - image.height
        bottom = float(image.height)

    left = max(0.0, left)
    top = max(0.0, top)
    right = min(float(image.width), right)
    bottom = min(float(image.height), bottom)

    return image.transform(
        (FRAME_WIDTH, FRAME_HEIGHT),
        Image.Transform.EXTENT,
        (left, top, right, bottom),
        resample=Image.Resampling.BICUBIC,
    )


def fit_text(title: str, subtitle: str) -> dict[str, object]:
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
        title_font = load_font(DEFAULT_TITLE_FONT, title_size)
        subtitle_font = load_font(DEFAULT_SUBTITLE_FONT, subtitle_size)
        title_lines = wrap_text(measure, title, title_font, max_text_width)
        subtitle_lines = wrap_text(measure, subtitle, subtitle_font, max_text_width)
        title_width, title_height, title_line_height = measure_block(measure, title_lines, title_font, title_spacing)
        subtitle_width, subtitle_height, subtitle_line_height = measure_block(
            measure, subtitle_lines, subtitle_font, subtitle_spacing
        )

        body_gap = gap if subtitle_lines else 0
        box_width = min(FRAME_WIDTH - 120, max(title_width, subtitle_width, 1) + pad_x * 2)
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


def draw_text_block(
    frame: Image.Image,
    text_spec: dict[str, object],
    time_s: float,
    progress: float,
    motion: str,
    brand: str,
) -> Image.Image:
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    card_intro = ease_out_back(fade_progress(time_s, 0.18, 0.95), overshoot=1.05)
    title_intro = ease_out_back(fade_progress(time_s, 0.38, 0.9), overshoot=1.0)
    subtitle_intro = ease_out_cubic(fade_progress(time_s, 0.95, 0.75))
    motion_peak = get_motion_emphasis(progress, motion)

    title_alpha = int(255 * max(0.0, min(1.0, title_intro)))
    subtitle_alpha = int(255 * max(0.0, min(1.0, subtitle_intro)))
    card_alpha = int(215 * max(0.0, min(1.0, card_intro)) * (0.96 + 0.04 * motion_peak))

    box_width = int(text_spec["box_width"])
    box_height = int(text_spec["box_height"])
    pad_x = int(text_spec["pad_x"])
    pad_y = int(text_spec["pad_y"])
    text_width = int(text_spec["text_width"])

    box_left = (FRAME_WIDTH - box_width) // 2
    entrance_offset = int((1.0 - card_intro) * 56)
    peak_lift = int(10 * motion_peak)
    box_top = int(FRAME_HEIGHT * 0.66 + entrance_offset - peak_lift)
    box_right = box_left + box_width
    box_bottom = box_top + box_height
    radius = 34

    shadow_alpha = int(56 * max(0.0, min(1.0, card_intro)) * (0.9 + 0.1 * motion_peak))
    draw.rounded_rectangle(
        (box_left, box_top + 12 + peak_lift // 2, box_right, box_bottom + 12 + peak_lift // 2),
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

    title_font = text_spec["title_font"]
    subtitle_font = text_spec["subtitle_font"]
    title_lines = text_spec["title_lines"]
    subtitle_lines = text_spec["subtitle_lines"]
    title_line_height = int(text_spec["title_line_height"])
    subtitle_line_height = int(text_spec["subtitle_line_height"])
    title_spacing = int(text_spec["title_spacing"])
    subtitle_spacing = int(text_spec["subtitle_spacing"])
    gap = int(text_spec["gap"])
    title_y_offset = int((1.0 - title_intro) * 24)
    subtitle_y_offset = int((1.0 - subtitle_intro) * 18)

    for line in title_lines:
        line_width = draw.textbbox((0, 0), line, font=title_font, stroke_width=2)[2]
        x = content_x + (text_width - line_width) // 2
        draw.text(
            (x, y + 2 + title_y_offset),
            line,
            font=title_font,
            fill=(255, 255, 255, min(120, title_alpha)),
            stroke_width=2,
            stroke_fill=(255, 255, 255, min(120, title_alpha)),
        )
        draw.text(
            (x, y + title_y_offset),
            line,
            font=title_font,
            fill=(64, 44, 32, title_alpha),
            stroke_width=2,
            stroke_fill=(64, 44, 32, title_alpha),
        )
        y += title_line_height + title_spacing

    if subtitle_lines:
        y += gap
        for line in subtitle_lines:
            line_width = draw.textbbox((0, 0), line, font=subtitle_font)[2]
            x = content_x + (text_width - line_width) // 2
            draw.text(
                (x, y + 2 + subtitle_y_offset),
                line,
                font=subtitle_font,
                fill=(255, 255, 255, min(100, subtitle_alpha)),
            )
            draw.text((x, y + subtitle_y_offset), line, font=subtitle_font, fill=(98, 76, 62, subtitle_alpha))
            y += subtitle_line_height + subtitle_spacing

    if brand:
        brand_alpha = int(200 * ease_out_cubic(fade_progress(time_s, 1.6, 0.8)))
        brand_font = load_font(DEFAULT_SUBTITLE_FONT, 30)
        brand_bbox = draw.textbbox((0, 0), brand, font=brand_font)
        brand_x = FRAME_WIDTH - 42 - (brand_bbox[2] - brand_bbox[0])
        brand_y = FRAME_HEIGHT - 58 - (brand_bbox[3] - brand_bbox[1])
        draw.text((brand_x, brand_y), brand, font=brand_font, fill=(244, 239, 234, brand_alpha))

    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def main() -> None:
    args = parse_args()
    image_path = args.image.expanduser().resolve()
    if not image_path.exists():
        raise SystemExit(f"Input image not found: {image_path}")

    title = args.title or title_from_stem(image_path.stem)
    output_path = args.output or Path("videos") / f"{image_path.stem}_tiktok.mp4"
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_image = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    text_spec = fit_text(title, args.subtitle)

    total_frames = max(1, int(args.duration * args.fps))
    writer = imageio.get_writer(
        output_path,
        fps=args.fps,
        codec="libx264",
        ffmpeg_log_level="error",
        macro_block_size=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )

    try:
        for frame_index in range(total_frames):
            progress = frame_index / max(1, total_frames - 1)
            time_s = frame_index / args.fps
            frame = render_cover_frame(base_image, progress, args.zoom_end, args.motion)
            frame = draw_text_block(frame, text_spec, time_s, progress, args.motion, args.brand)
            writer.append_data(np.asarray(frame))
    finally:
        writer.close()

    print(output_path)


if __name__ == "__main__":
    main()
