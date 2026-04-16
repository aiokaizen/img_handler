from enum import Enum

from PIL import Image, ImageOps


class OutputSize(str, Enum):
    PIN_2X3 = "pin_2x3"   # 1000x1500 — standard pin
    PIN_1X2 = "pin_1x2"   # 1000x2000 — tall pin


CANVAS_DIMENSIONS: dict[OutputSize, tuple[int, int]] = {
    OutputSize.PIN_2X3: (1000, 1500),
    OutputSize.PIN_1X2: (1000, 2000),
}


def resolve_output_size(value: str | OutputSize) -> OutputSize:
    if isinstance(value, OutputSize):
        return value
    try:
        return OutputSize(value)
    except ValueError as exc:
        valid = ", ".join(s.value for s in OutputSize)
        raise ValueError(f"Unsupported output_size {value!r} (valid: {valid})") from exc


def cover_crop(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """Resize+center-crop `image` so it exactly fills `target_size` (CSS 'cover')."""
    source = ImageOps.exif_transpose(image).convert("RGB")
    target_w, target_h = target_size
    src_w, src_h = source.size

    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        new_h = target_h
        new_w = max(target_w, int(round(src_w * (target_h / src_h))))
    else:
        new_w = target_w
        new_h = max(target_h, int(round(src_h * (target_w / src_w))))

    resized = source.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))
