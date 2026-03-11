from PIL import (
    Image,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageEnhance,
    ImageChops,
)

DEFAULT_FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEFAULT_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def apply_glass_title_brand(
    img: Image.Image,
    title: str,
    subtitle: str,
    brand: str = "nomadmouse.com",
) -> Image.Image:
    """
    iOS / iPhone-style glassmorphism:
      - Rounded frosted glass card with *backdrop blur + vibrancy*, specular highlight, rim lighting,
        subtle inner shadow, drop shadow, and fine grain.
      - Wrapped title/subtitle (multi-line) centered within the card.
      - Branding at bottom-right.

    Card height fits text tightly (plus padding); not forced square.
    """

    # ---------------- helpers ----------------
    def load_font(path: str, size: int) -> ImageFont.ImageFont:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    def line_height(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont) -> int:
        b = draw.textbbox((0, 0), "Ag", font=font)
        return max(1, b[3] - b[1])

    def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []

        out: list[str] = []
        for para in text.splitlines():
            para = para.strip()
            if not para:
                out.append("")
                continue

            words = para.split()
            cur = words[0]
            for w in words[1:]:
                cand = f"{cur} {w}"
                if draw.textbbox((0, 0), cand, font=font)[2] <= max_w:
                    cur = cand
                else:
                    out.append(cur)
                    cur = w

            # hard-wrap any single token still too wide
            while draw.textbbox((0, 0), cur, font=font)[2] > max_w and len(cur) > 1:
                cut = len(cur)
                while cut > 1 and draw.textbbox((0, 0), cur[:cut], font=font)[2] > max_w:
                    cut -= 1
                out.append(cur[:cut])
                cur = cur[cut:]
            out.append(cur)

        return out

    def multiline_height(draw: ImageDraw.ImageDraw, lines: list[str], font: ImageFont.ImageFont, spacing: int) -> int:
        if not lines:
            return 0
        lh = line_height(draw, font)
        return len(lines) * lh + (len(lines) - 1) * spacing

    def make_1d_gradient(length: int, top_to_bottom: bool = True, peak: int = 255) -> Image.Image:
        """Returns a 1xL L-mode gradient."""
        length = max(1, int(length))
        g = Image.new("L", (1, length), 0)
        if length == 1:
            g.putpixel((0, 0), peak)
            return g
        for y in range(length):
            t = y / (length - 1)
            v = int(peak * (1.0 - t) if top_to_bottom else peak * t)
            g.putpixel((0, y), v)
        return g

    # ---------------- normalize base ----------------
    img = ImageOps.exif_transpose(img).convert("RGBA")
    # keep a copy of the original for selective restoration of artifacts
    orig_img = img.copy()
    w, h = img.size

    # small canvas is enough for text measuring
    measure_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    # ---------------- card sizing (width fixed, height fits text) ----------------
    card_w = int(min(w, h) * 0.55)
    card_w = max(160, min(card_w, int(w * 0.92)))

    pad_x = int(card_w * 0.08)
    pad_top = int(card_w * 0.10)
    pad_bottom = int(card_w * 0.10)

    max_card_h = max(120, int(h * 0.80))

    title_size = int(card_w * 0.12)
    subtitle_size = int(card_w * 0.06)
    min_title_size = 14
    min_subtitle_size = 10

    gap = max(6, int(card_w * 0.04))

    for _ in range(16):
        title_font = load_font(DEFAULT_FONT_BOLD, title_size)
        subtitle_font = load_font(DEFAULT_FONT_REG, subtitle_size)

        title_ls = max(2, int(title_size * 0.20))
        subtitle_ls = max(2, int(subtitle_size * 0.25))
        text_max_w = max(20, card_w - 2 * pad_x)

        title_lines = wrap_text(measure_draw, title, title_font, text_max_w)
        subtitle_lines = wrap_text(measure_draw, subtitle, subtitle_font, text_max_w)

        title_h = multiline_height(measure_draw, title_lines, title_font, title_ls)
        subtitle_h = multiline_height(measure_draw, subtitle_lines, subtitle_font, subtitle_ls)

        needed_h = pad_top + title_h + (gap if subtitle_h else 0) + subtitle_h + pad_bottom

        if needed_h <= max_card_h:
            card_h = int(needed_h)
            break

        if title_size <= min_title_size and subtitle_size <= min_subtitle_size:
            card_h = int(min(needed_h, h - max(20, int(min(w, h) * 0.04))))
            break

        title_size = max(min_title_size, int(title_size * 0.92))
        subtitle_size = max(min_subtitle_size, int(subtitle_size * 0.92))
        gap = max(4, int(gap * 0.92))
        pad_top = max(10, int(pad_top * 0.98))
        pad_bottom = max(10, int(pad_bottom * 0.98))

    left = (w - card_w) // 2
    top = (h - card_h) // 2
    right = left + card_w
    bottom = top + card_h
    card_box = (left, top, right, bottom)

    card_min = min(card_w, card_h)

    # ---------------- iPhone-like glass styling parameters ----------------
    # Stronger blur + "vibrancy" (saturation/contrast) is key to iOS feel.
    blur_r = int(max(14, card_min * 0.085))
    border_w = max(2, int(card_min * 0.010))
    radius = int(card_min * 0.22)
    radius = max(14, min(radius, (card_min // 2) - 1))

    # Drop shadow behind the card (subtle)
    shadow_offset = max(2, int(card_min * 0.02))
    shadow_blur = int(max(10, card_min * 0.09))
    shadow_alpha = 80  # subtle

    # Fill tint (glass haze)
    glass_fill = (255, 255, 255, 45)

    # Rim lighting (top-left highlight + bottom-right shade)
    rim_strength = 110
    rim_shadow_strength = 70

    # Fine grain/noise
    grain_alpha = 10  # keep subtle

    # ---------------- build masks ----------------
    # Outer rounded mask
    outer_mask = Image.new("L", (card_w, card_h), 0)
    md = ImageDraw.Draw(outer_mask)
    md.rounded_rectangle((0, 0, card_w, card_h), radius=radius, fill=255)

    # Rim mask = outer - inner (a ring)
    inset = max(2, border_w)
    inner_mask = Image.new("L", (card_w, card_h), 0)
    md2 = ImageDraw.Draw(inner_mask)
    md2.rounded_rectangle(
        (inset, inset, card_w - inset, card_h - inset),
        radius=max(1, radius - inset),
        fill=255,
    )
    rim_mask = ImageChops.subtract(outer_mask, inner_mask)

    # ---------------- base image copy ----------------
    base = img.copy()

    # ---------------- drop shadow (behind the card) ----------------
    shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_shape = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(shadow_shape).rounded_rectangle((0, 0, card_w, card_h), radius=radius, fill=shadow_alpha)
    shadow_shape = shadow_shape.filter(ImageFilter.GaussianBlur(radius=shadow_blur))

    # Paste shadow with offset (down/right)
    shadow_layer.paste(
        Image.new("RGBA", (card_w, card_h), (0, 0, 0, 255)),
        (left + shadow_offset, top + shadow_offset),
        shadow_shape,
    )
    base = Image.alpha_composite(base, shadow_layer)

    # ---------------- backdrop blur + vibrancy (core iOS feel) ----------------
    # Expand the cropped region by a padding proportional to the blur radius
    # so the Gaussian blur samples outside the card bounds. This prevents
    # visible rectangular artifacts at the card edges caused by cropping
    # before blurring.
    pad_blur = max(blur_r * 2, 4)
    crop_left = max(0, left - pad_blur)
    crop_top = max(0, top - pad_blur)
    crop_right = min(w, right + pad_blur)
    crop_bottom = min(h, bottom + pad_blur)
    crop_box = (crop_left, crop_top, crop_right, crop_bottom)

    region = base.crop(crop_box)
    blurred_region = region.filter(ImageFilter.GaussianBlur(radius=blur_r))

    # Extract the exact card-sized portion from the blurred_region so it lines
    # up with the card box when pasted back onto the base image.
    off_x = left - crop_left
    off_y = top - crop_top
    blurred = blurred_region.crop((off_x, off_y, off_x + card_w, off_y + card_h))

    # Vibrancy-ish: boost saturation + contrast slightly; keep subtle
    blurred_rgb = blurred.convert("RGB")
    blurred_rgb = ImageEnhance.Color(blurred_rgb).enhance(1.25)
    blurred_rgb = ImageEnhance.Contrast(blurred_rgb).enhance(1.06)
    blurred_rgb = ImageEnhance.Brightness(blurred_rgb).enhance(1.02)
    blurred = blurred_rgb.convert("RGBA")

    # Paste blurred region clipped to rounded rect
    base.paste(blurred, card_box, outer_mask)

    # ---------------- glass overlay (haze + specular highlights + rims) ----------------
    # Build the glass card on a dedicated card-sized layer to avoid any drawing
    # bleeding outside the rounded rectangle (prevents visible artifacts at edges).
    card_surface = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card_surface)

    # Main translucent haze (drawn locally inside card_surface)
    cd.rounded_rectangle((0, 0, card_w, card_h), radius=radius, fill=glass_fill)

    # Specular highlight: combine the diagonal gradient with a large soft ellipse
    # to create a bigger, rounder, and more intentional highlight (not noisy).
    v = make_1d_gradient(card_h, top_to_bottom=True, peak=255).resize((card_w, card_h))
    hgrad = make_1d_gradient(card_w, top_to_bottom=True, peak=255).resize((card_h, card_w)).transpose(Image.ROTATE_90)
    diag = ImageChops.add(v, hgrad, scale=2.0)

    spec = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 0))
    # soft elliptical blob (larger, offset towards top-left)
    blob = Image.new("L", (card_w, card_h), 0)
    bd = ImageDraw.Draw(blob)
    blob_bbox = (-int(card_w * 0.15), -int(card_h * 0.10), int(card_w * 0.6), int(card_h * 0.6))
    bd.ellipse(blob_bbox, fill=255)
    blob = blob.filter(ImageFilter.GaussianBlur(radius=max(1, int(card_min * 0.14))))

    # combine diagonal fade with big blob and use a stronger multiplier for a clear spec
    spec_alpha = ImageChops.lighter(diag.point(lambda p: int(p * 0.42)), blob)
    spec.putalpha(spec_alpha)
    card_surface.paste(spec, (0, 0), spec)

    # Inner shadow gradient (bottom-right) for depth
    v2 = make_1d_gradient(card_h, top_to_bottom=False, peak=255).resize((card_w, card_h))
    h2 = make_1d_gradient(card_w, top_to_bottom=False, peak=255).resize((card_h, card_w)).transpose(Image.ROTATE_90)
    diag2 = ImageChops.add(v2, h2, scale=2.0)
    inner_shadow = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    inner_shadow.putalpha(diag2.point(lambda p: int(p * 0.12)))
    card_surface.paste(inner_shadow, (0, 0), inner_shadow)

    # Rim lighting (use the precomputed rim_mask to constrain to rim ring)
    rim_hi = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 0))
    rim_hi.putalpha(diag.point(lambda p: int(p * (rim_strength / 255.0))))
    card_surface.paste(rim_hi, (0, 0), rim_mask)

    rim_lo = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    rim_lo.putalpha(diag2.point(lambda p: int(p * (rim_shadow_strength / 255.0))))
    card_surface.paste(rim_lo, (0, 0), rim_mask)

    # A thin border to finish edges (drawn inside card_surface)
    cd.rounded_rectangle((0, 0, card_w, card_h), radius=radius, outline=(255, 255, 255, 90), width=border_w)

    # Fine grain inside the card (subtle): use per-pixel alpha from noise
    grain_l = Image.effect_noise((card_w, card_h), 18).point(lambda p: 128 + int((p - 128) * 0.35))
    grain = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 0))
    grain.putalpha(grain_l.point(lambda p: int(p * (grain_alpha / 255.0))))
    card_surface.paste(grain, (0, 0), card_surface)  # paste grain masked by card alpha

    # Composite the card_surface into a full-size overlay at the card position.
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    # Ensure card alpha strictly respects the rounded outer mask to prevent any
    # accidental drawing (speculars, grain, shadows) from bleeding outside the
    # rounded corners. Multiply will zero-out alpha where outer_mask is 0.
    card_alpha = card_surface.split()[-1]
    card_alpha = ImageChops.multiply(card_alpha, outer_mask)
    card_surface.putalpha(card_alpha)

    overlay.paste(card_surface, (left, top), card_surface)

    composed = Image.alpha_composite(base, overlay)

    # Detect and remove small backdrop artifacts outside the rounded card.
    # Compute a full-size mask of the rounded card and detect pixels where the
    # composed result differs noticeably from the original image. Restrict to
    # a narrow band around the card to avoid global changes, then restore
    # those pixels from the original image.
    mask_full = Image.new("L", base.size, 0)
    mask_full.paste(outer_mask, (left, top))

    inv_mask = ImageChops.invert(mask_full)

    # difference (grayscale) between composed and original
    diff = ImageChops.difference(composed.convert("RGB"), orig_img.convert("RGB")).convert("L")
    diff = diff.filter(ImageFilter.GaussianBlur(radius=2))
    thresh = diff.point(lambda p: 255 if p > 22 else 0)

    # candidate restoration areas: outside the rounded mask and above threshold
    candidates = ImageChops.multiply(inv_mask, thresh)

    # restrict to a narrow band around the card to avoid accidental wide changes
    pad_detect = max(4, int(card_min * 0.12))
    band = Image.new("L", base.size, 0)
    bd = ImageDraw.Draw(band)
    band_box = (
        max(0, left - pad_detect),
        max(0, top - pad_detect),
        min(w, right + pad_detect),
        min(h, bottom + pad_detect),
    )
    bd.rectangle(band_box, fill=255)
    candidates = ImageChops.multiply(candidates, band)

    # clean up small specks, then restore from original where candidates are set
    candidates = candidates.filter(ImageFilter.MaxFilter(5))

    composed.paste(orig_img, (0, 0), candidates)

    draw = ImageDraw.Draw(composed)

    # ---------------- draw wrapped title + subtitle centered ----------------
    title_font = load_font(DEFAULT_FONT_BOLD, title_size)
    subtitle_font = load_font(DEFAULT_FONT_REG, subtitle_size)
    title_ls = max(2, int(title_size * 0.20))
    subtitle_ls = max(2, int(subtitle_size * 0.25))

    text_center_x = left + card_w // 2
    y = top + pad_top

    shadow = (0, 0, 0, 95)
    title_col = (255, 255, 255, 240)
    subtitle_col = (255, 255, 255, 215)

    def draw_centered_lines(
        lines: list[str],
        font: ImageFont.ImageFont,
        fill: tuple[int, int, int, int],
        shadow_fill: tuple[int, int, int, int],
        y0: int,
        spacing: int,
    ) -> int:
        lh = line_height(draw, font)
        y = y0
        for line in lines:
            if line == "":
                y += lh + spacing
                continue
            tw = draw.textbbox((0, 0), line, font=font)[2]
            x = text_center_x - tw // 2
            draw.text((x + 2, y + 2), line, font=font, fill=shadow_fill)
            draw.text((x, y), line, font=font, fill=fill)
            y += lh + spacing
        return y - spacing if lines else y0

    y = draw_centered_lines(title_lines, title_font, title_col, shadow, y, title_ls)
    if subtitle_lines:
        y += gap
        _ = draw_centered_lines(subtitle_lines, subtitle_font, subtitle_col, shadow, y, subtitle_ls)

    # ---------------- branding bottom-right ----------------
    brand_size = max(10, int(min(w, h) * 0.035))
    brand_font = load_font(DEFAULT_FONT_REG, brand_size)
    pad = int(min(w, h) * 0.03)

    bb = draw.textbbox((0, 0), brand, font=brand_font)
    bw = bb[2] - bb[0]
    bh = bb[3] - bb[1]
    bx = w - pad - bw
    by = h - pad - bh

    draw.text((bx + 2, by + 2), brand, font=brand_font, fill=(0, 0, 0, 110))
    draw.text((bx, by), brand, font=brand_font, fill=(255, 255, 255, 205))

    return composed
