import math
from dataclasses import dataclass
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


MAX_ZOOM = 3.0


@dataclass(frozen=True)
class Framing:
    """How a photo sits in its slot.

    `zoom` crops tighter than the plain 'cover' fit (1.0 = no extra zoom).
    `focus_x` / `focus_y` are the point of the photo the crop centers on, as
    fractions of its width and height (0.5, 0.5 = the middle); the crop is
    pushed back inside the photo when the point is near an edge. `flip`
    mirrors the result left to right.
    """

    zoom: float = 1.0
    focus_x: float = 0.5
    focus_y: float = 0.5
    flip: bool = False

    def __post_init__(self):
        if not 1.0 <= self.zoom <= MAX_ZOOM:
            raise ValueError(f"zoom must be between 1.0 and {MAX_ZOOM}, not {self.zoom}")
        for name in ("focus_x", "focus_y"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0, not {value}")


DEFAULT_FRAMING = Framing()


def cover_crop(
    image: Image.Image,
    target_size: tuple[int, int],
    framing: Framing = DEFAULT_FRAMING,
) -> Image.Image:
    """Resize+crop `image` so it exactly fills `target_size` (CSS 'cover'), framed by `framing`."""
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

    if framing.zoom != 1.0:
        new_w, new_h = round(new_w * framing.zoom), round(new_h * framing.zoom)

    # Centered on the focus point, then pushed back inside the photo. The default
    # framing gives the same pixels as the plain centered crop always did.
    resized = source.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = min(max(math.floor(framing.focus_x * new_w - target_w / 2), 0), new_w - target_w)
    top = min(max(math.floor(framing.focus_y * new_h - target_h / 2), 0), new_h - target_h)
    panel = resized.crop((left, top, left + target_w, top + target_h))
    return ImageOps.mirror(panel) if framing.flip else panel
