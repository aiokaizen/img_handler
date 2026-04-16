from PIL import Image, ImageDraw, ImageFilter

from api_functions.effects import register_effect
from api_functions.effects.colors import parse_hex_color
from api_functions.effects.layout import (
    CANVAS_DIMENSIONS,
    OutputSize,
    cover_crop,
    resolve_output_size,
)
from api_functions.img_processing import (
    DEFAULT_CONDENSED_FONT,
    DEFAULT_SCRIPT_FONT,
    DEFAULT_SUBTITLE_FONT,
    DEFAULT_TITLE_ITALIC_FONT,
    load_font,
    measure_text_block,
    wrap_text,
)


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font,
    y: int,
    center_x: int,
    fill: tuple,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text((center_x - w // 2, y), text, font=font, fill=fill)


def _fit_lines(
    measure: ImageDraw.ImageDraw,
    text: str,
    *,
    font_path: str,
    font_variant: str | None,
    max_w: int,
    max_h: int,
    start_size: int,
    min_size: int,
    max_lines: int = 2,
) -> dict:
    size = start_size
    for _ in range(30):
        font = load_font(font_path, size, variant=font_variant)
        lines = wrap_text(measure, text, font, max_w)
        spacing = max(2, size // 12)
        _, h, lh = measure_text_block(measure, lines, font, spacing)
        fits = h <= max_h and len(lines) <= max_lines
        if fits or size <= min_size:
            return {
                "font": font, "lines": lines,
                "height": h, "line_height": lh,
                "spacing": spacing, "size": size,
            }
        size = max(min_size, int(size * 0.92))
    raise RuntimeError("unreachable: fit loop exited without returning")


def _brush_banner(
    canvas_size: tuple[int, int],
    *,
    center_xy: tuple[int, int],
    banner_w: int,
    banner_h: int,
    fill: tuple[int, int, int] = (250, 246, 239),
) -> Image.Image:
    """
    Soft-edged white pill sitting over the photo/bar seam. Approximates a hand-
    painted brush stroke: rounded pill + Gaussian-feathered alpha so the ends
    fade instead of terminating with a hard edge.
    """
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    mask = Image.new("L", canvas_size, 0)
    draw_mask = ImageDraw.Draw(mask)
    cx, cy = center_xy
    x0 = cx - banner_w // 2
    y0 = cy - banner_h // 2
    draw_mask.rounded_rectangle(
        (x0, y0, x0 + banner_w, y0 + banner_h),
        radius=banner_h // 2,
        fill=255,
    )
    # Feather edges into a paint-like soft transition.
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(3, banner_h // 14)))
    fill_layer = Image.new("RGBA", canvas_size, (*fill, 255))
    layer.paste(fill_layer, (0, 0), mask)
    return layer


@register_effect(
    "black_bar_triptych",
    kind="dual",
    description="Two photos split by a solid title bar, optional script accent banner and URL strip.",
)
def render(
    *,
    image_top: Image.Image,
    image_bottom: Image.Image,
    title: str,
    subtitle: str = "",
    accent_text: str = "",
    url_text: str = "",
    brand: str = "",
    band_fill_hex: str | None = None,
    band_text_hex: str | None = None,
    # Palette kwargs preserved for API-shape parity with other effects; unused here.
    primary_hex: str | None = None,
    secondary_hex: str | None = None,
    tertiary_hex: str | None = None,
    output_size: str | OutputSize = OutputSize.PIN_2X3,
) -> Image.Image:
    size = resolve_output_size(output_size)
    canvas_w, canvas_h = CANVAS_DIMENSIONS[size]

    band_fill = parse_hex_color(band_fill_hex) if band_fill_hex else (15, 15, 15)
    band_text = parse_hex_color(band_text_hex) if band_text_hex else (245, 245, 245)

    # --- Geometry (bar + optional URL strip centered, photos fill the rest) --
    bar_h = int(canvas_h * 0.22)
    url_h = int(canvas_h * 0.05) if url_text else 0
    bar_y = (canvas_h - bar_h - url_h) // 2
    url_y = bar_y + bar_h
    bottom_y = url_y + url_h
    top_h = bar_y
    bottom_h = canvas_h - bottom_y

    top_panel = cover_crop(image_top, (canvas_w, top_h))
    bottom_panel = cover_crop(image_bottom, (canvas_w, bottom_h))

    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    canvas.paste(top_panel, (0, 0))
    canvas.paste(bottom_panel, (0, bottom_y))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, bar_y, canvas_w, bar_y + bar_h), fill=band_fill)

    if url_text:
        draw.rectangle((0, url_y, canvas_w, url_y + url_h), fill=(250, 246, 239))

    # --- Title (+ optional subtitle inside bar) ------------------------------
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    inner_pad_x = int(canvas_w * 0.06)
    inner_pad_y = int(bar_h * 0.10)
    max_text_w = canvas_w - 2 * inner_pad_x

    subtitle_block = None
    if subtitle:
        subtitle_block = _fit_lines(
            measure, subtitle,
            font_path=DEFAULT_TITLE_ITALIC_FONT,
            font_variant="Italic",
            max_w=max_text_w,
            max_h=int(bar_h * 0.22),
            start_size=max(32, int(canvas_w * 0.04)),
            min_size=26,
            max_lines=1,
        )

    title_max_h = bar_h - 2 * inner_pad_y - (
        subtitle_block["height"] + max(8, bar_h // 30) if subtitle_block else 0
    )
    title_block = _fit_lines(
        measure, title.upper(),
        font_path=DEFAULT_CONDENSED_FONT,
        font_variant=None,
        max_w=max_text_w,
        max_h=title_max_h,
        start_size=max(120, int(canvas_w * 0.20)),
        min_size=70,
        max_lines=2,
    )

    gap_sub_to_title = max(8, bar_h // 30) if subtitle_block else 0
    total_block_h = (subtitle_block["height"] if subtitle_block else 0) + gap_sub_to_title + title_block["height"]
    content_y = bar_y + (bar_h - total_block_h) // 2
    center_x = canvas_w // 2

    y = content_y
    if subtitle_block:
        for line in subtitle_block["lines"]:
            _draw_centered(
                draw, line, font=subtitle_block["font"],
                y=y, center_x=center_x, fill=(*band_text, 255),
            )
            y += subtitle_block["line_height"] + subtitle_block["spacing"]
        y = content_y + subtitle_block["height"] + gap_sub_to_title

    for line in title_block["lines"]:
        _draw_centered(
            draw, line, font=title_block["font"],
            y=y, center_x=center_x, fill=(*band_text, 255),
        )
        y += title_block["line_height"] + title_block["spacing"]

    # --- URL strip text ------------------------------------------------------
    if url_text:
        url_size = max(24, int(url_h * 0.55))
        url_font = load_font(DEFAULT_SUBTITLE_FONT, url_size, variant="SemiBold")
        bbox = ImageDraw.Draw(canvas).textbbox((0, 0), url_text, font=url_font)
        text_h = bbox[3] - bbox[1]
        url_text_y = url_y + (url_h - text_h) // 2 - bbox[1]
        _draw_centered(
            draw, url_text, font=url_font,
            y=url_text_y, center_x=center_x, fill=(40, 36, 34),
        )

    # --- Accent banner (composited last so it overlays the bar seam) ---------
    composed = canvas.convert("RGBA")
    if accent_text:
        banner_h = max(70, int(canvas_h * 0.07))
        banner_w = int(canvas_w * 0.70)
        banner_center_y = bar_y  # banner centered on the photo/bar seam
        banner = _brush_banner(
            (canvas_w, canvas_h),
            center_xy=(center_x, banner_center_y),
            banner_w=banner_w,
            banner_h=banner_h,
        )
        composed = Image.alpha_composite(composed, banner)

        script_draw = ImageDraw.Draw(composed)
        script_size = max(44, int(banner_h * 0.78))
        # Shrink to fit the banner if the script text is long.
        for _ in range(12):
            script_font = load_font(DEFAULT_SCRIPT_FONT, script_size)
            bbox = script_draw.textbbox((0, 0), accent_text, font=script_font)
            if bbox[2] - bbox[0] <= int(banner_w * 0.90) or script_size <= 28:
                break
            script_size = int(script_size * 0.9)
        bbox = script_draw.textbbox((0, 0), accent_text, font=script_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = center_x - tw // 2
        ty = banner_center_y - th // 2 - bbox[1]
        script_draw.text((tx, ty), accent_text, font=script_font, fill=(28, 22, 18, 255))

    # --- Brand stamp (bottom right, outside the composed stack) --------------
    if brand:
        brand_size = max(18, canvas_w // 55)
        brand_font = load_font(DEFAULT_SUBTITLE_FONT, brand_size, variant="Medium")
        brand_draw = ImageDraw.Draw(composed)
        bbox = brand_draw.textbbox((0, 0), brand, font=brand_font)
        brand_w = bbox[2] - bbox[0]
        brand_h = bbox[3] - bbox[1]
        margin = max(20, canvas_w // 40)
        bx = canvas_w - margin - brand_w
        by = canvas_h - margin - brand_h
        brand_draw.text((bx, by), brand, font=brand_font, fill=(255, 255, 255, 230))

    return composed.convert("RGB")
