import time, base64, hashlib
from fastapi import UploadFile, HTTPException, Request
from fastapi.responses import FileResponse
from pathlib import Path, PurePath
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional
from slugify import slugify
from config.settings import (
    MAX_BYTES, UPLOAD_DIR, EXT_BY_MIME,
    PUBLIC_LINK_SECRET, PUBLIC_URL_TTL_SECONDS
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


def make_public_url(request, stored_filename: str, ttl_seconds: int = PUBLIC_URL_TTL_SECONDS) -> str:
    if not PUBLIC_LINK_SECRET:
        raise RuntimeError("PUBLIC_LINK_SECRET is not configured")

    expires = int(time.time()) + ttl_seconds
    uri = f"/images/public/{stored_filename}"

    # MUST match nginx secure_link_md5 string exactly:
    # "$secure_link_expires$uri <secret>"
    raw = f"{expires}{uri} {PUBLIC_LINK_SECRET}".encode("utf-8")

    sig = base64.urlsafe_b64encode(hashlib.md5(raw).digest()).decode("ascii").rstrip("=")

    # request.base_url includes scheme/host from nginx proxy headers
    return f"{str(request.base_url).rstrip('/')}{uri}?md5={sig}&expires={expires}"



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

    ttl_seconds = PUBLIC_URL_TTL_SECONDS
    public_url = make_public_url(request, stored_filename, ttl_seconds)
    expiry_timestamp = int(time.time()) + ttl_seconds
    expiry = datetime.fromtimestamp(expiry_timestamp, tz=timezone.utc).strftime("%d/%m/%Y %H:%M")

    return {
        "stored_filename": stored_filename,
        "image_url": str(image_url),  # protected
        "public_url": public_url,  # temporary, no auth
        "public_url_expiry": expiry
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