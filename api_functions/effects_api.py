import asyncio
import io
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile
from PIL import Image, UnidentifiedImageError

from api_functions.effects.black_bar import render as render_black_bar
from api_functions.effects.frosted_glass import render as render_frosted_glass
from api_functions.effects.layout import resolve_output_size
from api_functions.images import (
    add_timestamp_if_exists,
    make_public_url,
    read_and_validate_image_upload,
    slugified_filename,
)
from config.settings import PUBLIC_URL_TTL_SECONDS, UPLOAD_DIR

logger = logging.getLogger("uvicorn.error").getChild("img_handler.effects")


def _load_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Invalid image content") from exc
    return img


def _empty_to_none(value: str) -> str | None:
    value = (value or "").strip()
    return value or None


def _save_and_respond(
    request: Request,
    image: Image.Image,
    *,
    filename: str,
) -> dict:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=92, optimize=True, progressive=True)
    target_path = add_timestamp_if_exists(UPLOAD_DIR / filename)
    target_path.write_bytes(buf.getvalue())

    stored_filename = target_path.name
    image_url = request.url_for("get_image", filename=stored_filename)
    public_url = make_public_url(request, stored_filename, ttl_seconds=PUBLIC_URL_TTL_SECONDS)
    expiry_ts = int(time.time()) + PUBLIC_URL_TTL_SECONDS
    expiry = datetime.fromtimestamp(expiry_ts, tz=timezone.utc).strftime("%d/%m/%Y %H:%M")

    return {
        "stored_filename": stored_filename,
        "image_url": str(image_url),
        "public_url": public_url,
        "public_url_expiry": expiry,
    }


def _phase(label: str, effect: str, start: float) -> float:
    now = time.perf_counter()
    logger.info("effect=%s phase=%s elapsed_ms=%.1f", effect, label, (now - start) * 1000)
    return now


def _render_frosted_sync(
    *,
    request: Request,
    top_data: bytes,
    bottom_data: bytes,
    size,
    title: str,
    subtitle: str,
    brand: str,
    primary_hex: str | None,
    secondary_hex: str | None,
    tertiary_hex: str | None,
    top_filename: str,
    bottom_filename: str,
) -> dict:
    effect = "frosted_glass_triptych"
    t0 = time.perf_counter()
    top_img = _load_image(top_data)
    bottom_img = _load_image(bottom_data)
    logger.info(
        "effect=%s input_sizes top=%s bottom=%s",
        effect, top_img.size, bottom_img.size,
    )
    t = _phase("decode", effect, t0)

    try:
        result = render_frosted_glass(
            image_top=top_img,
            image_bottom=bottom_img,
            title=title,
            subtitle=subtitle,
            brand=brand,
            primary_hex=primary_hex,
            secondary_hex=secondary_hex,
            tertiary_hex=tertiary_hex,
            output_size=size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        top_img.close()
        bottom_img.close()
    t = _phase("render", effect, t)

    top_stem = Path(slugified_filename(top_filename)).stem
    bottom_stem = Path(slugified_filename(bottom_filename)).stem
    out_name = f"{top_stem}__{bottom_stem}_frosted_{size.value}.jpeg"

    response = _save_and_respond(request, result, filename=out_name)
    _phase("save", effect, t)
    logger.info("effect=%s total_ms=%.1f", effect, (time.perf_counter() - t0) * 1000)
    return response


def _render_black_bar_sync(
    *,
    request: Request,
    top_data: bytes,
    bottom_data: bytes,
    size,
    title: str,
    subtitle: str,
    accent_text: str,
    url_text: str,
    brand: str,
    band_fill_hex: str | None,
    band_text_hex: str | None,
    top_filename: str,
    bottom_filename: str,
) -> dict:
    effect = "black_bar_triptych"
    t0 = time.perf_counter()
    top_img = _load_image(top_data)
    bottom_img = _load_image(bottom_data)
    logger.info(
        "effect=%s input_sizes top=%s bottom=%s",
        effect, top_img.size, bottom_img.size,
    )
    t = _phase("decode", effect, t0)

    try:
        result = render_black_bar(
            image_top=top_img,
            image_bottom=bottom_img,
            title=title,
            subtitle=subtitle,
            accent_text=accent_text,
            url_text=url_text,
            brand=brand,
            band_fill_hex=band_fill_hex,
            band_text_hex=band_text_hex,
            output_size=size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        top_img.close()
        bottom_img.close()
    t = _phase("render", effect, t)

    top_stem = Path(slugified_filename(top_filename)).stem
    bottom_stem = Path(slugified_filename(bottom_filename)).stem
    out_name = f"{top_stem}__{bottom_stem}_blackbar_{size.value}.jpeg"

    response = _save_and_respond(request, result, filename=out_name)
    _phase("save", effect, t)
    logger.info("effect=%s total_ms=%.1f", effect, (time.perf_counter() - t0) * 1000)
    return response


async def apply_frosted_glass_triptych(
    request: Request,
    file_top: UploadFile,
    file_bottom: UploadFile,
    *,
    title: str,
    subtitle: str,
    brand: str,
    primary_hex: str,
    secondary_hex: str,
    tertiary_hex: str,
    output_size: str,
) -> dict:
    effect = "frosted_glass_triptych"
    logger.info("effect=%s received", effect)
    t0 = time.perf_counter()
    top_data, _ = await read_and_validate_image_upload(file_top)
    bottom_data, _ = await read_and_validate_image_upload(file_bottom)
    logger.info(
        "effect=%s upload_bytes top=%d bottom=%d receive_ms=%.1f",
        effect, len(top_data), len(bottom_data), (time.perf_counter() - t0) * 1000,
    )

    try:
        size = resolve_output_size(output_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await asyncio.to_thread(
        _render_frosted_sync,
        request=request,
        top_data=top_data,
        bottom_data=bottom_data,
        size=size,
        title=title,
        subtitle=subtitle,
        brand=brand,
        primary_hex=_empty_to_none(primary_hex),
        secondary_hex=_empty_to_none(secondary_hex),
        tertiary_hex=_empty_to_none(tertiary_hex),
        top_filename=file_top.filename,
        bottom_filename=file_bottom.filename,
    )


async def apply_black_bar_triptych(
    request: Request,
    file_top: UploadFile,
    file_bottom: UploadFile,
    *,
    title: str,
    subtitle: str,
    accent_text: str,
    url_text: str,
    brand: str,
    band_fill_hex: str,
    band_text_hex: str,
    output_size: str,
) -> dict:
    effect = "black_bar_triptych"
    logger.info("effect=%s received", effect)
    t0 = time.perf_counter()
    top_data, _ = await read_and_validate_image_upload(file_top)
    bottom_data, _ = await read_and_validate_image_upload(file_bottom)
    logger.info(
        "effect=%s upload_bytes top=%d bottom=%d receive_ms=%.1f",
        effect, len(top_data), len(bottom_data), (time.perf_counter() - t0) * 1000,
    )

    try:
        size = resolve_output_size(output_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await asyncio.to_thread(
        _render_black_bar_sync,
        request=request,
        top_data=top_data,
        bottom_data=bottom_data,
        size=size,
        title=title,
        subtitle=subtitle,
        accent_text=accent_text,
        url_text=url_text,
        brand=brand,
        band_fill_hex=_empty_to_none(band_fill_hex),
        band_text_hex=_empty_to_none(band_text_hex),
        top_filename=file_top.filename,
        bottom_filename=file_bottom.filename,
    )
