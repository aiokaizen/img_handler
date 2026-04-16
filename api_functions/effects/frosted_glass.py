from PIL import Image, ImageDraw, ImageFilter

from api_functions.effects import register_effect
from api_functions.effects.colors import derive_palette
from api_functions.effects.layout import (
    CANVAS_DIMENSIONS,
    OutputSize,
    cover_crop,
    resolve_output_size,
)
from api_functions.img_processing import (
    DEFAULT_BRAND_VARIANT,
    DEFAULT_SUBTITLE_FONT,
    DEFAULT_SUBTITLE_ITALIC_FONT,
    DEFAULT_SUBTITLE_VARIANT,
    DEFAULT_TITLE_FONT,
    DEFAULT_TITLE_VARIANT,
    load_font,
    measure_text_block,
    wrap_text,
)


def _fit_band_text(
    measure: ImageDraw.ImageDraw,
    title: str,
    subtitle: str,
    *,
    max_text_width: int,
    max_text_height: int,
    start_title_size: int,
    start_subtitle_size: int,
) -> dict:
    """Shrink title/subtitle until the combined block fits inside the band."""
    title_size = start_title_size
    subtitle_size = start_subtitle_size
    min_title = 42
    min_subtitle = 34

    for _ in range(30):
        title_font = load_font(DEFAULT_TITLE_FONT, title_size, variant=DEFAULT_TITLE_VARIANT)
        subtitle_font = load_font(
            DEFAULT_SUBTITLE_ITALIC_FONT, subtitle_size, variant="ExtraBold Italic",
        )

        title_lines = wrap_text(measure, title, title_font, max_text_width)
        subtitle_lines = (
            wrap_text(measure, subtitle, subtitle_font, max_text_width)
            if subtitle else []
        )

        title_spacing = max(4, title_size // 8)
        subtitle_spacing = max(3, subtitle_size // 8)
        rule_gap = max(54, title_size // 2) if subtitle_lines else 0

        _, title_h, title_lh = measure_text_block(measure, title_lines, title_font, title_spacing)
        _, subtitle_h, subtitle_lh = measure_text_block(
            measure, subtitle_lines, subtitle_font, subtitle_spacing,
        )
        total_h = title_h + rule_gap + subtitle_h

        fits = total_h <= max_text_height and len(title_lines) <= 3
        exhausted = title_size <= min_title and subtitle_size <= min_subtitle

        if fits or exhausted:
            return {
                "title_font": title_font,
                "subtitle_font": subtitle_font,
                "title_lines": title_lines,
                "subtitle_lines": subtitle_lines,
                "title_height": title_h,
                "subtitle_height": subtitle_h,
                "title_line_height": title_lh,
                "subtitle_line_height": subtitle_lh,
                "title_spacing": title_spacing,
                "subtitle_spacing": subtitle_spacing,
                "rule_gap": rule_gap,
                "total_height": total_h,
                "title_size": title_size,
            }

        title_size = max(min_title, int(title_size * 0.92))
        subtitle_size = max(min_subtitle, int(subtitle_size * 0.92))

    raise RuntimeError("unreachable: fit loop exited without returning")


def _draw_centered_line(
    draw: ImageDraw.ImageDraw,
    line: str,
    *,
    font,
    center_x: int,
    y: int,
    fill: tuple,
    shadow_fill: tuple | None = None,
) -> None:
    line_w = draw.textbbox((0, 0), line, font=font)[2]
    x = center_x - line_w // 2
    if shadow_fill is not None:
        draw.text((x + 2, y + 2), line, font=font, fill=shadow_fill)
    draw.text((x, y), line, font=font, fill=fill)


@register_effect(
    "frosted_glass_triptych",
    kind="dual",
    description="Two photos (top/bottom) separated by a centered frosted-glass title band.",
)
def render(
    *,
    image_top: Image.Image,
    image_bottom: Image.Image,
    title: str,
    subtitle: str = "",
    brand: str = "",
    primary_hex: str | None = None,
    secondary_hex: str | None = None,
    tertiary_hex: str | None = None,
    output_size: str | OutputSize = OutputSize.PIN_2X3,
) -> Image.Image:
    size = resolve_output_size(output_size)
    canvas_w, canvas_h = CANVAS_DIMENSIONS[size]

    # --- Build the base canvas (two photos stacked, no band yet) -------------
    half_h = canvas_h // 2
    top_panel = cover_crop(image_top, (canvas_w, half_h))
    bottom_panel = cover_crop(image_bottom, (canvas_w, canvas_h - half_h))

    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    canvas.paste(top_panel, (0, 0))
    canvas.paste(bottom_panel, (0, half_h))

    palette = derive_palette(
        top_panel,
        bottom_panel,
        primary_hex=primary_hex,
        secondary_hex=secondary_hex,
        tertiary_hex=tertiary_hex,
    )

    # --- Band geometry -------------------------------------------------------
    band_margin_x = int(canvas_w * 0.02)  # ~96% band width
    band_w = canvas_w - 2 * band_margin_x
    band_max_h = int(canvas_h * 0.32)
    band_pad_x = max(28, int(band_w * 0.08))
    band_pad_y = max(22, int(band_max_h * 0.16))

    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    fitted = _fit_band_text(
        measure,
        title,
        subtitle,
        max_text_width=band_w - 2 * band_pad_x,
        max_text_height=band_max_h - 2 * band_pad_y,
        start_title_size=max(72, int(canvas_w * 0.12)),
        start_subtitle_size=max(44, int(canvas_w * 0.05)),
    )

    band_h = min(band_max_h, fitted["total_height"] + 2 * band_pad_y)
    band_x = (canvas_w - band_w) // 2
    band_y = (canvas_h - band_h) // 2
    band_box = (band_x, band_y, band_x + band_w, band_y + band_h)
    band_radius = max(32, int(min(band_w, band_h) * 0.12))

    # --- Frosted glass: blur underlying canvas region and tint ---------------
    band_region = canvas.crop(band_box)
    blurred = band_region.filter(ImageFilter.GaussianBlur(radius=max(24, canvas_w // 45)))
    tinted = Image.blend(blurred, Image.new("RGB", blurred.size, palette["primary"]), 0.22)

    band_rgba = tinted.convert("RGBA")
    mask = Image.new("L", (band_w, band_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, band_w, band_h), radius=band_radius, fill=255)
    band_rgba.putalpha(mask)

    outline_layer = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
    outline_draw = ImageDraw.Draw(outline_layer)
    outline_draw.rounded_rectangle(
        (1, 1, band_w - 2, band_h - 2),
        radius=band_radius,
        outline=(*palette["primary"], 90),
        width=max(2, canvas_w // 400),
    )
    band_rgba = Image.alpha_composite(band_rgba, outline_layer)

    composed = canvas.convert("RGBA")
    composed.alpha_composite(band_rgba, (band_x, band_y))

    # --- Text ----------------------------------------------------------------
    draw = ImageDraw.Draw(composed)
    center_x = band_x + band_w // 2
    content_y = band_y + (band_h - fitted["total_height"]) // 2 - 40

    y = content_y
    for line in fitted["title_lines"]:
        _draw_centered_line(
            draw, line,
            font=fitted["title_font"],
            center_x=center_x,
            y=y,
            fill=(*palette["secondary"], 255),
        )
        y += fitted["title_line_height"] + fitted["title_spacing"]

    if fitted["subtitle_lines"]:
        # Thin accent rule between title and subtitle (Raffaello-style).
        # Uses secondary (text color) at low alpha so it stays visible on a
        # primary-tinted band — a primary-colored rule disappears into its
        # own background.
        rule_y = y - fitted["title_spacing"] + fitted["rule_gap"] * 3 // 5
        rule_margin = max(40, int(band_w * 0.22))
        draw.line(
            (band_x + rule_margin, rule_y, band_x + band_w - rule_margin, rule_y),
            fill=(*palette["secondary"], 110),
            width=max(2, canvas_w // 500),
        )
        sub_y = y - fitted["title_spacing"] + fitted["rule_gap"]
        for line in fitted["subtitle_lines"]:
            _draw_centered_line(
                draw, line,
                font=fitted["subtitle_font"],
                center_x=center_x,
                y=sub_y,
                fill=(*palette["tertiary"], 245),
            )
            sub_y += fitted["subtitle_line_height"] + fitted["subtitle_spacing"]

    # --- Brand stamp (bottom right, outside the band) ------------------------
    if brand:
        brand_size = max(18, canvas_w // 55)
        brand_font = load_font(DEFAULT_SUBTITLE_FONT, brand_size, variant=DEFAULT_BRAND_VARIANT)
        bbox = draw.textbbox((0, 0), brand, font=brand_font)
        brand_w = bbox[2] - bbox[0]
        brand_h = bbox[3] - bbox[1]
        margin = max(20, canvas_w // 40)
        bx = canvas_w - margin - brand_w
        by = canvas_h - margin - brand_h
        draw.text((bx, by), brand, font=brand_font, fill=(255, 255, 255, 230))

    return composed.convert("RGB")
