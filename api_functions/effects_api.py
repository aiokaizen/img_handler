import io
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
    top_data, _ = await read_and_validate_image_upload(file_top)
    bottom_data, _ = await read_and_validate_image_upload(file_bottom)

    try:
        size = resolve_output_size(output_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    top_img = _load_image(top_data)
    bottom_img = _load_image(bottom_data)

    try:
        result = render_frosted_glass(
            image_top=top_img,
            image_bottom=bottom_img,
            title=title,
            subtitle=subtitle,
            brand=brand,
            primary_hex=_empty_to_none(primary_hex),
            secondary_hex=_empty_to_none(secondary_hex),
            tertiary_hex=_empty_to_none(tertiary_hex),
            output_size=size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        top_img.close()
        bottom_img.close()

    top_stem = Path(slugified_filename(file_top.filename)).stem
    bottom_stem = Path(slugified_filename(file_bottom.filename)).stem
    out_name = f"{top_stem}__{bottom_stem}_frosted_{size.value}.jpeg"

    return _save_and_respond(request, result, filename=out_name)


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
    top_data, _ = await read_and_validate_image_upload(file_top)
    bottom_data, _ = await read_and_validate_image_upload(file_bottom)

    try:
        size = resolve_output_size(output_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    top_img = _load_image(top_data)
    bottom_img = _load_image(bottom_data)

    try:
        result = render_black_bar(
            image_top=top_img,
            image_bottom=bottom_img,
            title=title,
            subtitle=subtitle,
            accent_text=accent_text,
            url_text=url_text,
            brand=brand,
            band_fill_hex=_empty_to_none(band_fill_hex),
            band_text_hex=_empty_to_none(band_text_hex),
            output_size=size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        top_img.close()
        bottom_img.close()

    top_stem = Path(slugified_filename(file_top.filename)).stem
    bottom_stem = Path(slugified_filename(file_bottom.filename)).stem
    out_name = f"{top_stem}__{bottom_stem}_blackbar_{size.value}.jpeg"

    return _save_and_respond(request, result, filename=out_name)
