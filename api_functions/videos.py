import io
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from api_functions.images import (
    add_timestamp_if_exists,
    make_public_url,
    read_and_validate_image_upload,
    safe_filename,
    slugified_filename,
)
from config.settings import PUBLIC_URL_TTL_SECONDS, UPLOAD_DIR
from scripts.generate_recipe_tiktok_video import VALID_TRANSITIONS, generate_recipe_video


def get_single_video(filename: str):
    filename = safe_filename(filename)
    path = UPLOAD_DIR / filename

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(path)


async def create_recipe_video(
    request: Request,
    file: UploadFile,
    *,
    title: str,
    subtitle: str,
    ingredients: list[str],
    ingredients_title: str,
    brand: str,
    title_duration: float,
    ingredients_duration: float,
    transition: str,
    transition_duration: float,
    fps: int,
    zoom_peak: float,
):
    data, _ = await read_and_validate_image_upload(file)

    if transition not in VALID_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported transition '{transition}'")

    clean_ingredients = [item.strip() for item in ingredients if item.strip()]
    if not clean_ingredients:
        raise HTTPException(status_code=400, detail="At least one ingredient is required")

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Invalid image content") from exc

    slug_name = slugified_filename(file.filename)
    stem = Path(slug_name).stem
    target_path = add_timestamp_if_exists(UPLOAD_DIR / f"{stem}_recipe.mp4")

    try:
        generate_recipe_video(
            image,
            output_path=target_path,
            title=title,
            subtitle=subtitle,
            ingredients=clean_ingredients,
            ingredients_title=ingredients_title,
            brand=brand,
            title_duration=title_duration,
            ingredients_duration=ingredients_duration,
            transition=transition,
            transition_duration=transition_duration,
            fps=fps,
            zoom_peak=zoom_peak,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stored_filename = target_path.name
    video_url = request.url_for("get_video", filename=stored_filename)
    ttl_seconds = PUBLIC_URL_TTL_SECONDS
    public_url = make_public_url(
        request,
        stored_filename,
        public_prefix="/videos/public",
        ttl_seconds=ttl_seconds,
    )
    expiry_timestamp = int(time.time()) + ttl_seconds
    expiry = datetime.fromtimestamp(expiry_timestamp, tz=timezone.utc).strftime("%d/%m/%Y %H:%M")

    return {
        "stored_filename": stored_filename,
        "video_url": str(video_url),
        "public_url": public_url,
        "public_url_expiry": expiry,
        "transition": transition,
    }
