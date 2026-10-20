import math
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from api_functions.effects import register_effect
from api_functions.effects.colors import parse_hex_color
from api_functions.effects.layout import (
    CANVAS_DIMENSIONS,
    OutputSize,
    cover_crop,
    resolve_output_size,
)
from api_functions.img_processing import (
    BOUNCY_DISPLAY_FONT,
    BRUSH_SCRIPT_FONT,
    DEFAULT_SUBTITLE_FONT,
    GEOMETRIC_BOLD_FONT,
    GEOMETRIC_ITALIC_FONT,
    SERIF_DISPLAY_FONT,
    load_font,
)

# All geometry below is expressed as fractions of the canvas, measured from the
# 1:2 reference pins each style reproduces. Text is sized by cap height so the
# proportions hold across fonts.

INK = (12, 12, 12)
PANEL = (255, 255, 255)
WHITE = (255, 255, 255)

# Per-style accent: rules (ruled_band), banner (boxed_banner), inner frame
# (double_frame), footer strip (band_footer), band edges + script (diagonal_script).
DEFAULT_ACCENTS = {
    "ruled_band": (8, 8, 8),
    "boxed_banner": (215, 175, 111),
    "double_frame": (30, 30, 30),
    "band_footer": (0, 0, 0),
    "diagonal_script": (107, 36, 16),
}

BRAND_CENTER_Y = 0.9375
DIAGONAL_TILT_DEGREES = 13.5
DIAGONAL_SCRIPT_EXTRA_TILT = 3.0
SUPERSAMPLE = 2  # rotated layers are drawn at 2x, then downscaled


@dataclass(frozen=True)
class _Type:
    path: str
    variant: str | None = None
    axes: tuple[tuple[str, float], ...] = ()
    tracking: float = 0.0  # extra letter spacing, in em
    upper: bool = False

    def font(self, size: int) -> ImageFont.FreeTypeFont:
        return load_font(self.path, size, variant=self.variant, axes=dict(self.axes) or None)


SERIF = _Type(
    SERIF_DISPLAY_FONT,
    axes=(("Optical Size", 9), ("Weight", 700), ("Softness", 0), ("Wonky", 0)),
    tracking=0.04,
)
GEO_CAPS = _Type(GEOMETRIC_BOLD_FONT, tracking=0.06, upper=True)
GEO_ITALIC_CAPS = _Type(GEOMETRIC_ITALIC_FONT, tracking=0.14, upper=True)
BOUNCY_CAPS = _Type(BOUNCY_DISPLAY_FONT, upper=True)
SANS = _Type(DEFAULT_SUBTITLE_FONT, variant="Regular")
SANS_BRAND = _Type(DEFAULT_SUBTITLE_FONT, variant="Medium")
SANS_BOLD_CAPS = _Type(DEFAULT_SUBTITLE_FONT, variant="Bold", upper=True)
SANS_HEAVY_CAPS = _Type(DEFAULT_SUBTITLE_FONT, variant="ExtraBold", upper=True)
SCRIPT = _Type(BRUSH_SCRIPT_FONT)


@dataclass
class _Block:
    font: ImageFont.FreeTypeFont
    lines: list[str]
    pitch: int        # baseline to baseline
    tracking: float   # px
    width: int
    ink_top: int      # first line's ink top, relative to its baseline (negative)
    ink_bottom: int   # last line's ink bottom, relative to its baseline

    @property
    def height(self) -> int:
        return (len(self.lines) - 1) * self.pitch + self.ink_bottom - self.ink_top


@lru_cache(maxsize=None)
def _cap_ratio(t: _Type) -> float:
    """Cap height as a fraction of font size, so text can be sized by cap height."""
    top = t.font(1000).getbbox("H", anchor="ls")[1]
    return -top / 1000


def _line_width(font: ImageFont.FreeTypeFont, text: str, tracking: float) -> float:
    return font.getlength(text) + tracking * max(0, len(text) - 1)


def _split_balanced(words: tuple[str, ...], n: int, width) -> list[str]:
    """Split words into n lines, minimising the widest line."""

    @lru_cache(maxsize=None)
    def best(start: int, k: int) -> tuple[float, tuple[str, ...]]:
        if k == 1:
            line = " ".join(words[start:])
            return width(line), (line,)
        result = None
        for end in range(start + 1, len(words) - k + 2):
            line = " ".join(words[start:end])
            rest_w, rest = best(end, k - 1)
            candidate = (max(width(line), rest_w), (line, *rest))
            if result is None or candidate[0] < result[0]:
                result = candidate
        return result

    return list(best(0, n)[1])


def _wrap(text: str, font: ImageFont.FreeTypeFont, tracking: float, max_w: float) -> list[str]:
    """Fewest lines that fit max_w, balanced in width. Explicit newlines force breaks."""

    def width(s: str) -> float:
        return _line_width(font, s, tracking)

    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = tuple(paragraph.split())
        if not words:
            continue
        for n in range(1, len(words) + 1):
            split = _split_balanced(words, n, width)
            if max(width(line) for line in split) <= max_w:
                break
        lines.extend(split)
    return lines


def _measure(font: ImageFont.FreeTypeFont, lines: list[str], *, pitch: int, tracking: float) -> _Block:
    width = max(_line_width(font, line, tracking) for line in lines)
    return _Block(
        font=font,
        lines=lines,
        pitch=pitch,
        tracking=tracking,
        width=round(width),
        ink_top=font.getbbox(lines[0], anchor="ls")[1],
        ink_bottom=font.getbbox(lines[-1], anchor="ls")[3],
    )


def _layout(
    text: str,
    t: _Type,
    *,
    cap: float,
    max_w: float,
    max_lines: int = 1,
    pitch: float = 1.0,
    min_cap: float | None = None,
) -> _Block:
    """Size text by cap height (px), shrinking until it fits max_w and max_lines.

    `pitch` is the baseline-to-baseline distance as a multiple of cap height.
    Width is a hard limit. Text that still needs more lines after shrinking to
    75% gets one extra line rather than getting much smaller, and below
    `min_cap` it may overflow max_lines (the panels grow to fit).
    """
    text = text.upper() if t.upper else text
    min_cap = min_cap or cap * 0.5
    extra_line_at = cap * 0.75
    ratio = _cap_ratio(t)
    allowed_lines = max_lines
    while True:
        size = max(6, round(cap / ratio))
        font = t.font(size)
        tracking = t.tracking * size
        lines = _wrap(text, font, tracking, max_w)
        block = _measure(font, lines, pitch=round(cap * pitch), tracking=tracking)
        if block.width <= max_w and (len(lines) <= allowed_lines or cap <= min_cap):
            return block
        if size <= 6:
            return block
        if cap <= extra_line_at and allowed_lines == max_lines:
            allowed_lines += 1
        cap *= 0.94


def _draw_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    center_x: float,
    baseline: float,
    fill: tuple,
    tracking: float = 0.0,
) -> None:
    if not tracking:
        draw.text((center_x, baseline), text, font=font, fill=fill, anchor="ms")
        return
    # Place each glyph at its kerned position in the untracked line, plus the
    # accumulated tracking, so kerning pairs survive the extra spacing.
    x0 = center_x - _line_width(font, text, tracking) / 2
    for i, ch in enumerate(text):
        kerned_x = font.getlength(text[: i + 1]) - font.getlength(ch)
        draw.text((x0 + kerned_x + tracking * i, baseline), ch, font=font, fill=fill, anchor="ls")


def _draw_block(draw: ImageDraw.ImageDraw, block: _Block, *, center_x: float, top: float, fill: tuple) -> None:
    """Draw a block so its ink starts exactly at `top`."""
    baseline = top - block.ink_top
    for line in block.lines:
        _draw_line(
            draw, line,
            font=block.font, center_x=center_x, baseline=baseline,
            fill=fill, tracking=block.tracking,
        )
        baseline += block.pitch


def _photo_stack(
    image_top: Image.Image,
    image_bottom: Image.Image,
    size: tuple[int, int],
    *,
    top_h: int,
    bottom_y: int,
    bottom_h: int | None = None,
) -> Image.Image:
    w, h = size
    bottom_h = h - bottom_y if bottom_h is None else bottom_h
    canvas = Image.new("RGB", size, PANEL)
    canvas.paste(cover_crop(image_bottom, (w, bottom_h)), (0, bottom_y))
    canvas.paste(cover_crop(image_top, (w, top_h)), (0, 0))
    return canvas


def _paste_rotated(canvas: Image.Image, layer: Image.Image, *, center: tuple[float, float], degrees: float) -> None:
    """Rotate a SUPERSAMPLE-scale RGBA layer, downscale it, and paste it centered."""
    # Premultiplied alpha keeps the antialiased edges from picking up dark fringes.
    rotated = layer.convert("RGBa").rotate(degrees, resample=Image.Resampling.BICUBIC, expand=True)
    rotated = rotated.resize(
        (round(rotated.width / SUPERSAMPLE), round(rotated.height / SUPERSAMPLE)),
        Image.Resampling.LANCZOS,
    ).convert("RGBA")
    x = round(center[0] - rotated.width / 2)
    y = round(center[1] - rotated.height / 2)
    canvas.paste(rotated, (x, y), rotated)


def _draw_brand(canvas: Image.Image, brand: str, *, center_y: float) -> None:
    w, h = canvas.size
    block = _layout(brand, SANS_BRAND, cap=h * 0.0101, max_w=w * 0.6)
    draw = ImageDraw.Draw(canvas, "RGBA")
    top = round(center_y - block.height / 2)
    offset = max(1, round(h * 0.001))
    _draw_block(draw, block, center_x=w / 2 + offset, top=top + offset, fill=(0, 0, 0, 90))
    _draw_block(draw, block, center_x=w / 2, top=top, fill=(255, 255, 255, 240))


def _ruled_band(image_top, image_bottom, size, *, title, subtitle, accent):
    """Full-width white band between two black rules, serif title, outlined badge on the lower rule."""
    w, h = size
    rule = max(3, round(h * 0.003))
    pad = round(h * 0.0135)
    title_block = _layout(title, SERIF, cap=h * 0.0355, max_w=w * 0.84, max_lines=2, pitch=1.38)

    badge = None
    if subtitle:
        badge_pad_x = round(w * 0.032)
        badge_h = round(h * 0.0375)
        badge = _layout(subtitle, SERIF, cap=h * 0.0138, max_w=w * 0.8 - 2 * badge_pad_x)
        lower = round(h * 0.009) + badge_h // 2
    else:
        lower = pad

    band_h = 2 * rule + pad + title_block.height + lower
    band_top = round(h * 0.495 - band_h / 2)
    band_bottom = band_top + band_h

    canvas = _photo_stack(image_top, image_bottom, size, top_h=band_top, bottom_y=band_bottom)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, band_top, w, band_bottom - 1), fill=accent)
    draw.rectangle((0, band_top + rule, w, band_bottom - rule - 1), fill=PANEL)
    _draw_block(draw, title_block, center_x=w / 2, top=band_top + rule + pad, fill=INK)

    if badge:
        border = max(2, round(h * 0.0025))
        badge_w = badge.width + 2 * badge_pad_x
        x0 = (w - badge_w) // 2
        y0 = round(band_bottom - rule / 2 - badge_h / 2)
        draw.rectangle((x0, y0, x0 + badge_w, y0 + badge_h), fill=PANEL, outline=accent, width=border)
        _draw_block(draw, badge, center_x=w / 2, top=y0 + (badge_h - badge.height) / 2, fill=INK)

    return canvas, h * BRAND_CENTER_Y


def _boxed_banner(image_top, image_bottom, size, *, title, subtitle, accent):
    """Inset white box with a black border, bold caps title, colored banner across the bottom border."""
    w, h = size
    border = max(4, round(w * 0.0068))
    inset = round(w * 0.041)
    title_block = _layout(title, GEO_CAPS, cap=h * 0.0326, max_w=w * 0.82, max_lines=3, pitch=2.03)

    banner = None
    if subtitle:
        banner_w = round(w * 0.842)
        banner_h = round(h * 0.049)
        banner = _layout(subtitle, GEO_ITALIC_CAPS, cap=h * 0.0155, max_w=banner_w * 0.9)
        pad_top = round(h * 0.0095)
        pad_bottom = round(h * 0.019) + banner_h // 2
    else:
        pad_top = pad_bottom = round(h * 0.014)

    box_h = 2 * border + pad_top + title_block.height + pad_bottom
    box_top = round(h * 0.5 - box_h / 2)
    box_bottom = box_top + box_h

    seam = h // 2
    canvas = _photo_stack(image_top, image_bottom, size, top_h=seam, bottom_y=seam)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((inset, box_top, w - inset - 1, box_bottom - 1), fill=PANEL, outline=INK, width=border)
    _draw_block(draw, title_block, center_x=w / 2, top=box_top + border + pad_top, fill=INK)

    if banner:
        x0 = (w - banner_w) // 2
        y0 = round(box_bottom - border / 2 - banner_h / 2)
        draw.rectangle((x0, y0, x0 + banner_w - 1, y0 + banner_h - 1), fill=accent)
        top = y0 + (banner_h - banner.height) / 2
        shadow = max(1, round(h * 0.0012))
        _draw_block(draw, banner, center_x=w / 2 + shadow, top=top + shadow, fill=(0, 0, 0, 70))
        _draw_block(draw, banner, center_x=w / 2, top=top, fill=WHITE)

    return canvas, h * BRAND_CENTER_Y


def _double_frame(image_top, image_bottom, size, *, title, subtitle, accent):
    """Inset white panel with an inner hairline frame, light kicker line over a chunky caps title."""
    w, h = size
    outer_x = round(w * 0.02)
    frame_x = round(w * 0.026)
    frame_y = round(w * 0.012)
    rule = max(3, round(w * 0.0041))
    max_w = w * 0.86
    pad_top = round(h * 0.015)
    pad_bottom = round(h * 0.0177)
    kicker_gap = round(h * 0.0238)

    kicker = _layout(subtitle, SANS, cap=h * 0.031, max_w=max_w) if subtitle else None
    title_block = _layout(title, BOUNCY_CAPS, cap=h * 0.041, max_w=max_w, max_lines=2, pitch=1.6)
    content_h = title_block.height + (kicker.height + kicker_gap if kicker else 0)

    panel_h = 2 * (frame_y + rule) + pad_top + content_h + pad_bottom
    panel_top = round(h * 0.512 - panel_h / 2)
    panel_bottom = panel_top + panel_h

    seam = panel_top + panel_h // 2
    canvas = _photo_stack(image_top, image_bottom, size, top_h=seam, bottom_y=seam)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((outer_x, panel_top, w - outer_x - 1, panel_bottom - 1), fill=PANEL)
    draw.rectangle(
        (outer_x + frame_x, panel_top + frame_y, w - outer_x - frame_x - 1, panel_bottom - frame_y - 1),
        outline=accent, width=rule,
    )

    y = panel_top + frame_y + rule + pad_top
    if kicker:
        _draw_block(draw, kicker, center_x=w / 2, top=y, fill=(34, 34, 34))
        y += kicker.height + kicker_gap
    _draw_block(draw, title_block, center_x=w / 2, top=y, fill=(26, 26, 26))

    return canvas, h * BRAND_CENTER_Y


def _band_footer(image_top, image_bottom, size, *, title, subtitle, accent):
    """Plain full-width white band with heavy caps title, solid footer strip with a short call to action."""
    w, h = size
    pad_top = round(h * 0.019)
    pad_bottom = round(h * 0.014)
    title_block = _layout(title, SANS_HEAVY_CAPS, cap=h * 0.0358, max_w=w * 0.92, max_lines=2, pitch=1.51)

    band_h = pad_top + title_block.height + pad_bottom
    band_top = round(h * 0.479 - band_h / 2)
    band_bottom = band_top + band_h
    footer_h = round(h * 0.04) if subtitle else 0

    canvas = _photo_stack(
        image_top, image_bottom, size,
        top_h=band_top, bottom_y=band_bottom, bottom_h=h - footer_h - band_bottom,
    )
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, band_top, w, band_bottom - 1), fill=PANEL)
    _draw_block(draw, title_block, center_x=w / 2, top=band_top + pad_top, fill=INK)

    if subtitle:
        footer = _layout(subtitle, SANS_BOLD_CAPS, cap=h * 0.0142, max_w=w * 0.9)
        draw.rectangle((0, h - footer_h, w, h), fill=accent)
        _draw_block(draw, footer, center_x=w / 2, top=h - footer_h + (footer_h - footer.height) / 2, fill=WHITE)

    return canvas, h - footer_h - h * 0.04


def _diagonal_script(image_top, image_bottom, size, *, title, subtitle, accent):
    """White band tilted up to the right with colored edges, script sticker riding its top edge."""
    w, h = size
    ss = SUPERSAMPLE
    theta = math.radians(DIAGONAL_TILT_DEGREES)
    cx, cy = w / 2, h / 2

    # Photos meet along the band's centerline, which the band then covers.
    left_y = cy + math.tan(theta) * cx
    right_y = cy - math.tan(theta) * cx
    top_h = math.ceil(left_y)
    bottom_y = math.floor(right_y)
    canvas = Image.new("RGB", size, PANEL)
    canvas.paste(cover_crop(image_bottom, (w, h - bottom_y)), (0, bottom_y))
    mask = Image.new("L", (w, top_h), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (w, 0), (w, right_y), (0, left_y)], fill=255)
    canvas.paste(cover_crop(image_top, (w, top_h)), (0, 0), mask)

    # Band, drawn flat at supersample scale and long enough to span the canvas once tilted.
    edge = max(4, round(h * 0.005)) * ss
    pad = round(h * 0.0305) * ss
    title_block = _layout(
        title, SANS_HEAVY_CAPS,
        cap=h * 0.0288 * ss, max_w=w * 0.80 * ss, max_lines=2, pitch=1.83,
    )
    band_h = 2 * (edge + pad) + title_block.height
    strip_w = round(w * 1.6) * ss
    strip = Image.new("RGBA", (strip_w, band_h), (*accent, 255))
    strip_draw = ImageDraw.Draw(strip)
    strip_draw.rectangle((0, edge, strip_w, band_h - edge - 1), fill=PANEL)
    _draw_block(strip_draw, title_block, center_x=strip_w / 2, top=edge + pad, fill=INK)
    _paste_rotated(canvas, strip, center=(cx, cy), degrees=DIAGONAL_TILT_DEGREES)

    if subtitle:
        script = _layout(subtitle, SCRIPT, cap=h * 0.037 * ss, max_w=w * 0.62 * ss)
        line = script.lines[0]
        # The brush face is lighter than the reference sticker: fatten it with a
        # same-color stroke, then wrap everything in a white outline.
        weight = max(1, round(w * 0.0022)) * ss
        stroke = max(2, round(w * 0.009)) * ss + weight
        left, top, right, bottom = script.font.getbbox(line, anchor="ls", stroke_width=stroke)
        layer = Image.new("RGBA", (right - left + 2 * stroke, bottom - top + 2 * stroke), (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        origin = (stroke - left, stroke - top)
        layer_draw.text(origin, line, font=script.font, fill=WHITE, anchor="ls", stroke_width=stroke, stroke_fill=WHITE)
        layer_draw.text(origin, line, font=script.font, fill=accent, anchor="ls", stroke_width=weight, stroke_fill=accent)
        # Sit the sticker's center just above the band's top edge, along the band normal.
        lift = band_h / ss / 2 + h * 0.016
        center = (cx - math.sin(theta) * lift, cy - math.cos(theta) * lift)
        _paste_rotated(canvas, layer, center=center, degrees=DIAGONAL_TILT_DEGREES + DIAGONAL_SCRIPT_EXTRA_TILT)

    return canvas, h * BRAND_CENTER_Y


_STYLES = {
    "ruled_band": _ruled_band,
    "boxed_banner": _boxed_banner,
    "double_frame": _double_frame,
    "band_footer": _band_footer,
    "diagonal_script": _diagonal_script,
}
VALID_STYLES = tuple(_STYLES)


@register_effect(
    "title_panel_triptych",
    kind="dual",
    description="Two photos split by a white title panel, in one of five layouts picked by `style`.",
)
def render(
    *,
    image_top: Image.Image,
    image_bottom: Image.Image,
    title: str,
    subtitle: str = "",
    brand: str = "",
    style: str = "ruled_band",
    accent_hex: str | None = None,
    # Palette kwargs preserved for API-shape parity with other effects; unused here.
    primary_hex: str | None = None,
    secondary_hex: str | None = None,
    tertiary_hex: str | None = None,
    output_size: str | OutputSize = OutputSize.PIN_1X2,
) -> Image.Image:
    """
    Styles (`subtitle` fills each style's secondary slot):
      ruled_band       outlined badge on the band's lower rule
      boxed_banner     colored banner across the box's bottom border
      double_frame     light kicker line above the title
      band_footer      footer strip at the bottom of the pin
      diagonal_script  script sticker on the band's top edge

    `accent_hex` overrides the style's accent color. A newline in `title`
    forces a line break.
    """
    if style not in _STYLES:
        raise ValueError(f"Unsupported style {style!r} (valid: {', '.join(VALID_STYLES)})")
    if not (title or "").strip():
        raise ValueError("Title must not be empty")

    size = CANVAS_DIMENSIONS[resolve_output_size(output_size)]
    accent = parse_hex_color(accent_hex) if accent_hex else DEFAULT_ACCENTS[style]

    canvas, brand_y = _STYLES[style](
        image_top, image_bottom, size,
        title=title.strip(),
        subtitle=(subtitle or "").strip(),
        accent=accent,
    )
    if brand and brand.strip():
        _draw_brand(canvas, brand.strip(), center_y=brand_y)
    return canvas
