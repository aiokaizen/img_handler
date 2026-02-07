from fastapi import UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from pathlib import Path, PurePath
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional
from slugify import slugify
from config.settings import (
    MAX_BYTES, UPLOAD_DIR, EXT_BY_MIME
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def detect_image_ext(data: bytes) -> Optional[str]:
    # JPEG: FF D8 FF
    if len(data) >= 3 and data[0:3] == b"\xFF\xD8\xFF":
        return ".jpg"

    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if len(data) >= 8 and data[0:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"

    # GIF: GIF87a or GIF89a
    if len(data) >= 6 and data[0:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"

    # WebP: RIFF....WEBP
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"

    return None


def slugified_filename(original: str) -> str:
    # drop any path components
    name = PurePath(original).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")

    p = Path(name)
    stem, suffix = p.stem, p.suffix.lower()

    slug = slugify(stem, separator="-")
    if not slug:
        raise HTTPException(status_code=400, detail="Filename cannot be slugified")

    return f"{slug}{suffix}"


def safe_filename(original: str) -> str:
    # Drops any path components (prevents path traversal like ../../etc/passwd)
    name = PurePath(original).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return name


def add_timestamp_if_exists(path: Path) -> Path:
    if not path.exists():
        return path

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")  # microseconds to reduce collisions
    stem = path.stem
    suffix = path.suffix
    candidate = path.with_name(f"{stem}_{ts}{suffix}")

    # Extremely unlikely, but just in case:
    if candidate.exists():
        candidate = path.with_name(f"{stem}_{ts}_{uuid4().hex}{suffix}")

    return candidate


async def upload_single_image(request: Request, file: UploadFile):
    data = await file.read()
    await file.close()

    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    detected_ext = detect_image_ext(data)
    if detected_ext is None:
        raise HTTPException(status_code=400, detail="Invalid image content")

    # Keep the original filename, but enforce that extension matches the actual bytes
    original_name = safe_filename(file.filename)
    original_path = Path(original_name)
    original_ext = original_path.suffix.lower()

    expected_ext = EXT_BY_MIME[file.content_type]
    if original_ext not in {expected_ext, detected_ext}:
        raise HTTPException(
            status_code=400,
            detail=f"Filename extension '{original_ext}' does not match uploaded image type",
        )

    slug_name = slugified_filename(file.filename)
    target_path = add_timestamp_if_exists(UPLOAD_DIR / slug_name)
    target_path.write_bytes(data)
    stored_filename = target_path.name
    image_url = request.url_for("get_image", filename=stored_filename)

    return {
        "stored_as": stored_filename,
        "bytes": len(data),
        "image_url": str(image_url),
    }


def get_single_image(filename: str):
    filename = safe_filename(filename)
    path = UPLOAD_DIR / filename
    print("UPLOAD_DIR:", UPLOAD_DIR)
    print("path:", path)

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    # FileResponse sets a reasonable Content-Type based on filename extension
    return FileResponse(path)