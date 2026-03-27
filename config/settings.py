import os
from pathlib import Path

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")  # set in systemd Environment=

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

PUBLIC_LINK_SECRET = os.getenv("PUBLIC_LINK_SECRET", "")

PUBLIC_URL_TTL_SECONDS = int(os.getenv("PUBLIC_URL_TTL_SECONDS", "864000"))  # Defaults to 10 Days

VIDEO_JOBS_DIR = Path(os.getenv("VIDEO_JOBS_DIR", str(UPLOAD_DIR / "_video_jobs")))
VIDEO_JOB_WORKERS = int(os.getenv("VIDEO_JOB_WORKERS", "1"))
VIDEO_JOB_SWEEP_INTERVAL_SECONDS = float(os.getenv("VIDEO_JOB_SWEEP_INTERVAL_SECONDS", "5"))
WEBHOOK_TIMEOUT_SECONDS = float(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "10"))
WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", "5"))
