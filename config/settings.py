import os
from pathlib import Path

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "ddd")  # set in systemd Environment=

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/var/lib/img_handler/uploads"))

MAX_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}

EXT_BY_MIME = {
    "image/jpeg": ".jpeg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif"
}