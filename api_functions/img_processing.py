from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

DEFAULT_TITLE_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
DEFAULT_SUBTITLE_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

VALID_POSITIONS = {"top", "center", "bottom"}
VALID_THEMES = {"warm_light", "sage", "mocha"}
VALID_TITLE_ALIGNS = {"center", "left"}

THEMES = {
    "warm_light": {
        "box_fill": (252, 248, 242, 224),
        "box_outline": (131, 109, 93, 34),
        "shadow_fill": (64, 48, 38, 36),
        "title_color": (61, 45, 36, 255),
        "subtitle_color": (96, 78, 67, 255),
        "brand_color": (122, 102, 88, 180),
        "accent_color": (173, 139, 111, 105),
        "text_shadow": (255, 255, 255, 90),
    },
    "sage": {
        "box_fill": (244, 248, 241, 220),
        "box_outline": (111, 132, 114, 38),
        "shadow_fill": (49, 63, 51, 30),
        "title_color": (45, 63, 49, 255),
        "subtitle_color": (88, 104, 89, 255),
        "brand_color": (92, 111, 95, 175),
        "accent_color": (130, 156, 136, 105),
        "text_shadow": (255, 255, 255, 90),
    },
    "mocha": {
        "box_fill": (248, 241, 235, 224),
        "box_outline": (126, 97, 77, 40),
        "shadow_fill": (55, 37, 28, 38),
        "title_color": (73, 47, 34, 255),
        "subtitle_color": (111, 83, 65, 255),
        "brand_color": (131, 101, 82, 180),
        "accent_color": (168, 123, 92, 110),
        "text_shadow": (255, 255, 255, 85),
    },
}


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


def measure_text_block(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
    spacing: int,
) -> tuple[int, int, int]:
    if not lines:
        return 0, 0, 0

    bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_height = bbox[3] - bbox[1]
    width = max(draw.textbbox((0, 0), line, font=font)[2] for line in lines)
    height = len(lines) * line_height + max(0, len(lines) - 1) * spacing
    return width, height, line_height


def draw_text_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    *,
    font: ImageFont.ImageFont,
    start_x: int,
    start_y: int,
    max_width: int,
    line_height: int,
    spacing: int,
    fill: tuple[int, int, int, int],
    shadow_fill: tuple[int, int, int, int],
    align: str,
    stroke_width: int = 0,
) -> int:
    y = start_y
    for line in lines:
        line_width = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)[2]
        x = start_x + (max_width - line_width) // 2 if align == "center" else start_x
        draw.text((x, y + 1), line, font=font, fill=shadow_fill, stroke_width=stroke_width, stroke_fill=shadow_fill)
        draw.text((x, y), line, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=fill)
        y += line_height + spacing
    return y


def resolve_position_inputs(position: str, theme: str, title_align: str) -> tuple[str, dict[str, tuple[int, int, int, int]], str]:
    resolved_position = position or "top"
    resolved_theme = theme or "warm_light"
    resolved_align = title_align or "center"
    return resolved_position, THEMES[resolved_theme], resolved_align


def fit_text_layout(
    measure: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    title: str,
    subtitle: str,
) -> dict[str, object]:
    max_box_width = int(width * 0.88)
    max_box_height = int(height * 0.34)

    pad_x = max(28, int(width * 0.036))
    pad_y = max(22, int(height * 0.02))
    max_text_width = max(120, max_box_width - pad_x * 2)

    title_size = max(42, int(width * 0.082))
    subtitle_size = max(22, int(width * 0.04))
    title_spacing = max(4, int(title_size * 0.12))
    subtitle_spacing = max(3, int(subtitle_size * 0.16))
    gap = max(12, int(height * 0.016))
    accent_gap = max(12, int(height * 0.012))

    min_title_size = 24
    min_subtitle_size = 16

    fitted = None
    for _ in range(20):
        title_font = load_font(DEFAULT_TITLE_FONT, title_size)
        subtitle_font = load_font(DEFAULT_SUBTITLE_FONT, subtitle_size)

        title_lines = wrap_text(measure, title, title_font, max_text_width)
        subtitle_lines = wrap_text(measure, subtitle, subtitle_font, max_text_width)

        title_width, title_height, title_line_height = measure_text_block(measure, title_lines, title_font, title_spacing)
        subtitle_width, subtitle_height, subtitle_line_height = measure_text_block(
            measure, subtitle_lines, subtitle_font, subtitle_spacing
        )

        inner_width = max(title_width, subtitle_width, 1)
        box_width = min(max_box_width, inner_width + pad_x * 2)
        body_gap = gap if subtitle_lines else 0
        divider_gap = accent_gap if subtitle_lines else 0
        box_height = title_height + subtitle_height + body_gap + divider_gap + pad_y * 2

        fitted = {
            "title_font": title_font,
            "subtitle_font": subtitle_font,
            "title_lines": title_lines,
            "subtitle_lines": subtitle_lines,
            "title_width": title_width,
            "subtitle_width": subtitle_width,
            "title_height": title_height,
            "subtitle_height": subtitle_height,
            "title_line_height": title_line_height,
            "subtitle_line_height": subtitle_line_height,
            "title_spacing": title_spacing,
            "subtitle_spacing": subtitle_spacing,
            "gap": body_gap,
            "divider_gap": divider_gap,
            "pad_x": pad_x,
            "pad_y": pad_y,
            "box_width": box_width,
            "box_height": box_height,
            "text_width": box_width - pad_x * 2,
        }

        if box_height <= max_box_height and len(title_lines) <= 4 and len(subtitle_lines) <= 4:
            return fitted

        if title_size <= min_title_size and subtitle_size <= min_subtitle_size:
            return fitted

        title_size = max(min_title_size, int(title_size * 0.92))
        subtitle_size = max(min_subtitle_size, int(subtitle_size * 0.92))
        title_spacing = max(3, int(title_spacing * 0.92))
        subtitle_spacing = max(2, int(subtitle_spacing * 0.92))
        gap = max(8, int(gap * 0.92))
        accent_gap = max(8, int(accent_gap * 0.92))

    return fitted if fitted is not None else {}


def get_box_top(position: str, image_height: int, box_height: int) -> int:
    margin = max(28, int(image_height * 0.06))
    usable_top = margin
    usable_bottom = max(margin, image_height - margin - box_height)

    if position == "center":
        return max(usable_top, (image_height - box_height) // 2)
    if position == "bottom":
        return usable_bottom
    return usable_top


def apply_title_layout(
    img: Image.Image,
    title: str,
    subtitle: str,
    brand: str = "nomadmouse.com",
    position: str = "top",
    theme: str = "warm_light",
    title_align: str = "center",
) -> Image.Image:
    """
    Editorial text treatment for vertical food photography.

    The renderer uses a single card style and anchors it at the top, center,
    or bottom of the frame. Text is measured before drawing so the final title
    and subtitle stay inside the card bounds.
    """

    img = ImageOps.exif_transpose(img).convert("RGBA")
    width, height = img.size
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    position, palette, title_align = resolve_position_inputs(position, theme, title_align)
    fitted = fit_text_layout(measure, width=width, height=height, title=title, subtitle=subtitle)

    title_font = fitted["title_font"]
    subtitle_font = fitted["subtitle_font"]
    title_lines = fitted["title_lines"]
    subtitle_lines = fitted["subtitle_lines"]
    title_height = fitted["title_height"]
    title_line_height = fitted["title_line_height"]
    subtitle_line_height = fitted["subtitle_line_height"]
    title_spacing = fitted["title_spacing"]
    subtitle_spacing = fitted["subtitle_spacing"]
    gap = fitted["gap"]
    divider_gap = fitted["divider_gap"]
    pad_x = fitted["pad_x"]
    pad_y = fitted["pad_y"]
    box_width = fitted["box_width"]
    box_height = fitted["box_height"]
    text_width = fitted["text_width"]

    box_left = (width - box_width) // 2
    box_top = get_box_top(position, height, box_height)
    box_right = box_left + box_width
    box_bottom = box_top + box_height
    radius = max(18, int(min(box_width, box_height) * 0.08))

    composed = img.copy()
    overlay = Image.new("RGBA", composed.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", composed.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    shadow_draw = ImageDraw.Draw(shadow)

    shadow_draw.rounded_rectangle(
        (box_left, box_top + 8, box_right, box_bottom + 8),
        radius=radius,
        fill=palette["shadow_fill"],
    )
    overlay_draw.rounded_rectangle(
        (box_left, box_top, box_right, box_bottom),
        radius=radius,
        fill=palette["box_fill"],
        outline=palette["box_outline"],
        width=max(1, int(width * 0.002)),
    )

    accent_y = box_top + pad_y + title_height + divider_gap // 2
    if subtitle_lines:
        accent_margin = max(40, int(box_width * 0.24))
        overlay_draw.line(
            (box_left + accent_margin, accent_y, box_right - accent_margin, accent_y),
            fill=palette["accent_color"],
            width=max(2, int(width * 0.003)),
        )

    composed = Image.alpha_composite(
        composed,
        shadow.filter(ImageFilter.GaussianBlur(radius=max(8, int(width * 0.01)))),
    )
    composed = Image.alpha_composite(composed, overlay)
    draw = ImageDraw.Draw(composed)

    content_x = box_left + pad_x
    content_y = box_top + pad_y
    title_stroke_width = max(1, int(width * 0.0016))

    y = draw_text_lines(
        draw,
        title_lines,
        font=title_font,
        start_x=content_x,
        start_y=content_y,
        max_width=text_width,
        line_height=title_line_height,
        spacing=title_spacing,
        fill=palette["title_color"],
        shadow_fill=palette["text_shadow"],
        align=title_align,
        stroke_width=title_stroke_width,
    )

    if subtitle_lines:
        subtitle_y = y + gap
        draw_text_lines(
            draw,
            subtitle_lines,
            font=subtitle_font,
            start_x=content_x,
            start_y=subtitle_y,
            max_width=text_width,
            line_height=subtitle_line_height,
            spacing=subtitle_spacing,
            fill=palette["subtitle_color"],
            shadow_fill=palette["text_shadow"],
            align=title_align,
        )

    if brand:
        brand_size = max(14, int(width * 0.022))
        brand_font = load_font(DEFAULT_SUBTITLE_FONT, brand_size)
        brand_bbox = draw.textbbox((0, 0), brand, font=brand_font)
        brand_width = brand_bbox[2] - brand_bbox[0]
        brand_height = brand_bbox[3] - brand_bbox[1]
        brand_margin = max(20, int(width * 0.035))
        brand_x = width - brand_margin - brand_width
        brand_y = height - brand_margin - brand_height
        draw.text((brand_x, brand_y), brand, font=brand_font, fill=palette["brand_color"])

    return composed
