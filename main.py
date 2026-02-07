from fastapi import FastAPI, UploadFile, File, HTTPException
from pathlib import Path
from uuid import uuid4

app = FastAPI()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def detect_image_ext(data: bytes) -> str | None:
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


@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    # Basic allowlist on declared MIME
    if not file.content_type or file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Unsupported media type")

    data = await file.read()
    await file.close()

    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    ext = detect_image_ext(data)
    if ext is None:
        raise HTTPException(status_code=400, detail="Invalid image content")

    filename = f"{uuid4().hex}{ext}"
    path = UPLOAD_DIR / filename

    path.write_bytes(data)

    return {
        "stored_as": filename,
        "path": str(path),
        "bytes": len(data),
        "declared_content_type": file.content_type,
    }
