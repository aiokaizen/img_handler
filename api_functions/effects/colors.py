import re

from PIL import Image


HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def parse_hex_color(value: str) -> tuple[int, int, int]:
    match = HEX_RE.match((value or "").strip())
    if not match:
        raise ValueError(f"Invalid hex color {value!r} (expected '#rrggbb')")
    raw = match.group(1)
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def luminance(rgb: tuple[int, int, int]) -> float:
    """Perceived luminance, 0 (black) .. 1 (white). sRGB coefficients."""
    r, g, b = (c / 255.0 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrasting_text_color(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """Near-black on light backgrounds, warm off-white on dark ones."""
    return (28, 22, 18) if luminance(bg) > 0.55 else (250, 248, 243)


def _rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def extract_dominant_colors(
    *source_images: Image.Image,
    k: int = 5,
    sample_size: int = 100,
) -> list[tuple[int, int, int]]:
    """
    Downscale every input to a common square sample, composite side-by-side,
    median-cut quantize, drop near-white/near-black clusters, return remaining
    cluster centers ordered by frequency descending.

    Passing multiple images blends their color distributions in a single
    quantization pass — useful when the recipe's palette lives in two photos.
    """
    if not source_images:
        return []

    thumbs = [
        img.convert("RGB").resize((sample_size, sample_size), Image.Resampling.LANCZOS)
        for img in source_images
    ]
    if len(thumbs) == 1:
        combined = thumbs[0]
    else:
        combined = Image.new("RGB", (sample_size * len(thumbs), sample_size))
        for i, thumb in enumerate(thumbs):
            combined.paste(thumb, (i * sample_size, 0))

    quantized = combined.quantize(
        colors=k,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    palette = quantized.getpalette() or []
    counts = quantized.getcolors() or []

    clusters: list[tuple[int, tuple[int, int, int]]] = []
    for count, index in counts:
        base = index * 3
        if base + 2 >= len(palette):
            continue
        rgb_value = (palette[base], palette[base + 1], palette[base + 2])
        lum = luminance(rgb_value)
        if lum < 0.08 or lum > 0.94:
            continue
        clusters.append((count, rgb_value))

    clusters.sort(reverse=True, key=lambda entry: entry[0])
    return [rgb_value for _, rgb_value in clusters]


def derive_palette(
    *source_images: Image.Image,
    primary_hex: str | None = None,
    secondary_hex: str | None = None,
    tertiary_hex: str | None = None,
) -> dict[str, tuple[int, int, int]]:
    """
    Resolve the (primary, secondary, tertiary) palette.

    - primary  : recipe accent color (auto-extracted from source_images if not given)
    - secondary: title text color    (contrast-derived from primary if not given)
    - tertiary : subtitle/brand color (defaults to secondary; overridable)

    Passing multiple source images blends their palettes before extraction.
    """
    extracted = extract_dominant_colors(*source_images) if primary_hex is None else []

    if primary_hex:
        primary = parse_hex_color(primary_hex)
    elif extracted:
        primary = extracted[0]
    else:
        primary = (200, 150, 130)  # warm neutral fallback

    if secondary_hex:
        secondary = parse_hex_color(secondary_hex)
    else:
        secondary = contrasting_text_color(primary)

    # Default tertiary to secondary so subtitles stay legible on the primary-tinted
    # band. Explicit override via tertiary_hex is for effects that need a third
    # visually distinct color (URL strips, accent labels).
    tertiary = parse_hex_color(tertiary_hex) if tertiary_hex else secondary

    return {"primary": primary, "secondary": secondary, "tertiary": tertiary}
