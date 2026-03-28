import io
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from fastapi import HTTPException, Request, UploadFile
from PIL import Image, UnidentifiedImageError

from api_functions.images import (
    add_timestamp_if_exists,
    build_absolute_url,
    make_public_url_from_base,
    read_and_validate_image_upload,
    slugified_filename,
)
from config.settings import (
    PUBLIC_URL_TTL_SECONDS,
    UPLOAD_DIR,
    VIDEO_JOB_SWEEP_INTERVAL_SECONDS,
    VIDEO_JOB_WORKERS,
    VIDEO_JOBS_DIR,
    WEBHOOK_MAX_ATTEMPTS,
    WEBHOOK_TIMEOUT_SECONDS,
)
from scripts.generate_recipe_tiktok_video import VALID_TRANSITIONS, generate_recipe_video


VIDEO_JOBS_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("uvicorn.error").getChild("img_handler.video_jobs")

GENERATION_EXECUTOR: ThreadPoolExecutor | None = None
CALLBACK_EXECUTOR: ThreadPoolExecutor | None = None

JOB_FILE_LOCK = threading.Lock()
ACTIVE_JOB_IDS: set[str] = set()
ACTIVE_CALLBACK_IDS: set[str] = set()
ACTIVE_LOCK = threading.Lock()
SCHEDULER_LOCK = threading.RLock()
SCHEDULER_THREAD: threading.Thread | None = None
SCHEDULER_STARTED = False
SCHEDULER_STOP = threading.Event()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed


def compute_retry_delay_seconds(attempt: int) -> int:
    return min(300, 5 * (2 ** max(0, attempt - 1)))


def job_age_seconds(job: dict[str, Any]) -> float:
    created_at = parse_iso(job.get("created_at"))
    if created_at is None:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds())


def job_dir(job_id: str) -> Path:
    return VIDEO_JOBS_DIR / job_id


def job_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def write_job_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def read_job_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_job(job_id: str) -> dict[str, Any]:
    path = job_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video job not found")

    with JOB_FILE_LOCK:
        return read_job_file(path)


def mutate_job(job_id: str, mutator) -> dict[str, Any]:
    path = job_path(job_id)
    with JOB_FILE_LOCK:
        job = read_job_file(path)
        mutator(job)
        job["updated_at"] = now_utc_iso()
        write_job_file(path, job)
        return job


def sanitize_job(job: dict[str, Any]) -> dict[str, Any]:
    callback = job.get("callback") or {}
    public_callback = None
    if callback.get("url"):
        public_callback = {
            "url": callback.get("url"),
            "status": callback.get("status"),
            "attempts": callback.get("attempts", 0),
            "last_attempt_at": callback.get("last_attempt_at"),
            "next_attempt_at": callback.get("next_attempt_at"),
            "last_status_code": callback.get("last_status_code"),
            "last_error": callback.get("last_error"),
            "delivered_at": callback.get("delivered_at"),
        }

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "status_url": job["status_url"],
        "result": job.get("result"),
        "error": job.get("error"),
        "callback": public_callback,
    }


def validate_callback_url(callback_url: str) -> str:
    cleaned = callback_url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="callback_url must be a valid http or https URL")
    return cleaned


def build_callback_payload(job: dict[str, Any]) -> dict[str, Any]:
    event = "video.recipe.completed" if job["status"] == "completed" else "video.recipe.failed"
    return {
        "event": event,
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "status_url": job["status_url"],
        "result": job.get("result"),
        "error": job.get("error"),
    }


def should_attempt_callback(job: dict[str, Any]) -> bool:
    if job.get("status") not in {"completed", "failed"}:
        return False

    callback = job.get("callback") or {}
    if not callback.get("url"):
        return False
    if callback.get("status") not in {"pending", "retry_scheduled"}:
        return False

    next_attempt_at = parse_iso(callback.get("next_attempt_at"))
    if next_attempt_at is None:
        return True

    return next_attempt_at <= datetime.now(timezone.utc)


def mark_job_active(job_id: str, active_set: set[str]) -> bool:
    with ACTIVE_LOCK:
        if job_id in active_set:
            return False
        active_set.add(job_id)
        return True


def unmark_job_active(job_id: str, active_set: set[str]) -> None:
    with ACTIVE_LOCK:
        active_set.discard(job_id)


def schedule_generation(job_id: str) -> None:
    if not mark_job_active(job_id, ACTIVE_JOB_IDS):
        return

    def run() -> None:
        try:
            process_recipe_video_job(job_id)
        finally:
            unmark_job_active(job_id, ACTIVE_JOB_IDS)

    executor = get_generation_executor()
    if executor is None:
        unmark_job_active(job_id, ACTIVE_JOB_IDS)
        return

    executor.submit(run)


def schedule_callback(job_id: str) -> None:
    if not mark_job_active(job_id, ACTIVE_CALLBACK_IDS):
        return

    def run() -> None:
        try:
            deliver_job_callback(job_id)
        finally:
            unmark_job_active(job_id, ACTIVE_CALLBACK_IDS)

    executor = get_callback_executor()
    if executor is None:
        unmark_job_active(job_id, ACTIVE_CALLBACK_IDS)
        return

    executor.submit(run)


def sweep_jobs_once() -> None:
    for path in VIDEO_JOBS_DIR.glob("*/job.json"):
        try:
            job = read_job_file(path)
        except (OSError, json.JSONDecodeError):
            continue

        if job.get("status") in {"queued", "processing"}:
            schedule_generation(job["job_id"])
            continue

        if should_attempt_callback(job):
            schedule_callback(job["job_id"])


def scheduler_loop() -> None:
    sweep_jobs_once()
    while not SCHEDULER_STOP.wait(VIDEO_JOB_SWEEP_INTERVAL_SECONDS):
        sweep_jobs_once()


def get_generation_executor() -> ThreadPoolExecutor:
    global GENERATION_EXECUTOR
    with SCHEDULER_LOCK:
        if GENERATION_EXECUTOR is None:
            GENERATION_EXECUTOR = ThreadPoolExecutor(
                max_workers=max(1, VIDEO_JOB_WORKERS),
                thread_name_prefix="video-job",
            )
        return GENERATION_EXECUTOR


def get_callback_executor() -> ThreadPoolExecutor:
    global CALLBACK_EXECUTOR
    with SCHEDULER_LOCK:
        if CALLBACK_EXECUTOR is None:
            CALLBACK_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-callback")
        return CALLBACK_EXECUTOR


def start_video_job_scheduler() -> None:
    global SCHEDULER_THREAD, SCHEDULER_STARTED

    with SCHEDULER_LOCK:
        if SCHEDULER_STARTED:
            return

        get_generation_executor()
        get_callback_executor()
        SCHEDULER_STOP.clear()
        SCHEDULER_THREAD = threading.Thread(
            target=scheduler_loop,
            name="video-job-scheduler",
            daemon=True,
        )
        SCHEDULER_THREAD.start()
        SCHEDULER_STARTED = True
        logger.info("Started video job scheduler with jobs_dir=%s", VIDEO_JOBS_DIR)


def stop_video_job_scheduler() -> None:
    global CALLBACK_EXECUTOR, GENERATION_EXECUTOR, SCHEDULER_STARTED, SCHEDULER_THREAD

    SCHEDULER_STOP.set()
    if SCHEDULER_THREAD is not None:
        SCHEDULER_THREAD.join(timeout=1)
        SCHEDULER_THREAD = None

    if GENERATION_EXECUTOR is not None:
        GENERATION_EXECUTOR.shutdown(wait=True, cancel_futures=False)
        GENERATION_EXECUTOR = None

    if CALLBACK_EXECUTOR is not None:
        CALLBACK_EXECUTOR.shutdown(wait=True, cancel_futures=False)
        CALLBACK_EXECUTOR = None

    with ACTIVE_LOCK:
        ACTIVE_JOB_IDS.clear()
        ACTIVE_CALLBACK_IDS.clear()

    SCHEDULER_STARTED = False
    logger.info("Stopped video job scheduler")


def build_video_result(base_url: str, stored_filename: str) -> dict[str, str]:
    ttl_seconds = PUBLIC_URL_TTL_SECONDS
    expiry_timestamp = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
    expiry = datetime.fromtimestamp(expiry_timestamp, tz=timezone.utc).strftime("%d/%m/%Y %H:%M")

    return {
        "stored_filename": stored_filename,
        "video_url": build_absolute_url(base_url, f"/videos/{stored_filename}"),
        "public_url": make_public_url_from_base(
            base_url,
            stored_filename,
            public_prefix="/videos/public",
            ttl_seconds=ttl_seconds,
        ),
        "public_url_expiry": expiry,
    }


def process_recipe_video_job(job_id: str) -> None:
    job_snapshot = load_job(job_id)
    if job_snapshot.get("status") not in {"queued", "processing"}:
        return

    logger.info(
        "Starting recipe video job job_id=%s callback_url=%s queued_for_seconds=%.2f",
        job_id,
        (job_snapshot.get("callback") or {}).get("url") or "-",
        job_age_seconds(job_snapshot),
    )

    mutate_job(
        job_id,
        lambda job: (
            job.__setitem__("status", "processing"),
            job.__setitem__("error", None),
        ),
    )

    target_path: Path | None = None

    try:
        job = load_job(job_id)
        source_path = Path(job["source"]["path"])
        with Image.open(source_path) as image:
            image.load()
            loaded_image = image.copy()

        stem = job["source"]["slug_stem"]
        target_path = add_timestamp_if_exists(UPLOAD_DIR / f"{stem}_recipe.mp4")
        params = job["parameters"]

        generate_recipe_video(
            loaded_image,
            output_path=target_path,
            title=params["title"],
            subtitle=params["subtitle"],
            ingredients=params["ingredients"],
            ingredients_title=params["ingredients_title"],
            brand=params["brand"],
            title_duration=params["title_duration"],
            ingredients_duration=params["ingredients_duration"],
            transition=params["transition"],
            transition_duration=params["transition_duration"],
            fps=params["fps"],
            zoom_peak=params["zoom_peak"],
        )

        result = build_video_result(job["base_url"], target_path.name)
        result["transition"] = params["transition"]

        completed_job = mutate_job(
            job_id,
            lambda current: (
                current.__setitem__("status", "completed"),
                current.__setitem__("error", None),
                current.__setitem__("result", result),
                current["callback"].__setitem__(
                    "next_attempt_at",
                    now_utc_iso() if current["callback"].get("url") else None,
                ),
            ),
        )
        logger.info(
            "Completed recipe video job job_id=%s stored_filename=%s total_seconds=%.2f callback_url=%s",
            job_id,
            target_path.name,
            job_age_seconds(completed_job),
            (completed_job.get("callback") or {}).get("url") or "-",
        )
    except Exception as exc:
        if target_path and target_path.exists():
            target_path.unlink(missing_ok=True)

        failed_job = mutate_job(
            job_id,
            lambda current: (
                current.__setitem__("status", "failed"),
                current.__setitem__("result", None),
                current.__setitem__("error", {"message": str(exc)}),
                current["callback"].__setitem__(
                    "next_attempt_at",
                    now_utc_iso() if current["callback"].get("url") else None,
                ),
            ),
        )
        logger.exception(
            "Recipe video job failed job_id=%s total_seconds=%.2f callback_url=%s error=%s",
            job_id,
            job_age_seconds(failed_job),
            (failed_job.get("callback") or {}).get("url") or "-",
            exc,
        )
    finally:
        latest = load_job(job_id)
        if should_attempt_callback(latest):
            schedule_callback(job_id)


def deliver_job_callback(job_id: str) -> None:
    job = load_job(job_id)
    if not should_attempt_callback(job):
        return

    callback = job["callback"]
    attempt_number = callback.get("attempts", 0) + 1
    logger.info(
        "Firing webhook callback job_id=%s attempt=%s callback_url=%s total_seconds=%.2f",
        job_id,
        attempt_number,
        callback["url"],
        job_age_seconds(job),
    )
    payload = build_callback_payload(job)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "img-handler-webhook/1.0",
        "X-Img-Handler-Event": payload["event"],
        "X-Img-Handler-Job-Id": job_id,
    }

    bearer_token = callback.get("bearer_token")
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    body = json.dumps(payload).encode("utf-8")
    request = UrlRequest(callback["url"], data=body, headers=headers, method="POST")

    status_code = None
    error_message = None
    try:
        with urlopen(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:
            status_code = response.status
    except HTTPError as exc:
        status_code = exc.code
        error_message = f"HTTP {exc.code}"
    except URLError as exc:
        error_message = str(exc.reason)
    except OSError as exc:
        error_message = str(exc)

    attempt_time = now_utc_iso()
    if status_code is not None and 200 <= status_code < 300:
        delivered_job = mutate_job(
            job_id,
            lambda current: (
                current["callback"].__setitem__("status", "delivered"),
                current["callback"].__setitem__("attempts", current["callback"].get("attempts", 0) + 1),
                current["callback"].__setitem__("last_attempt_at", attempt_time),
                current["callback"].__setitem__("last_status_code", status_code),
                current["callback"].__setitem__("last_error", None),
                current["callback"].__setitem__("next_attempt_at", None),
                current["callback"].__setitem__("delivered_at", attempt_time),
            ),
        )
        logger.info(
            "Delivered webhook callback job_id=%s attempt=%s callback_url=%s status_code=%s total_seconds=%.2f",
            job_id,
            attempt_number,
            callback["url"],
            status_code,
            job_age_seconds(delivered_job),
        )
        return

    def mark_retry(current: dict[str, Any]) -> None:
        callback_data = current["callback"]
        attempts = callback_data.get("attempts", 0) + 1
        callback_data["attempts"] = attempts
        callback_data["last_attempt_at"] = attempt_time
        callback_data["last_status_code"] = status_code
        callback_data["last_error"] = error_message or "Callback delivery failed"
        callback_data["delivered_at"] = None

        if attempts >= WEBHOOK_MAX_ATTEMPTS:
            callback_data["status"] = "failed"
            callback_data["next_attempt_at"] = None
            return

        retry_at = datetime.now(timezone.utc) + timedelta(seconds=compute_retry_delay_seconds(attempts))
        callback_data["status"] = "retry_scheduled"
        callback_data["next_attempt_at"] = retry_at.isoformat()

    retried_job = mutate_job(job_id, mark_retry)
    retry_callback = retried_job["callback"]
    log_method = logger.warning if retry_callback.get("status") == "failed" else logger.info
    log_method(
        "Webhook callback attempt failed job_id=%s attempt=%s callback_url=%s last_status_code=%s last_error=%s next_attempt_at=%s total_seconds=%.2f",
        job_id,
        attempt_number,
        callback["url"],
        retry_callback.get("last_status_code"),
        retry_callback.get("last_error"),
        retry_callback.get("next_attempt_at"),
        job_age_seconds(retried_job),
    )


async def create_recipe_video_job(
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
    callback_url: str,
    callback_bearer_token: str,
) -> dict[str, Any]:
    data, detected_ext = await read_and_validate_image_upload(file)

    if transition not in VALID_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported transition '{transition}'")
    if title_duration <= 0 or ingredients_duration <= 0:
        raise HTTPException(status_code=400, detail="Durations must be greater than zero")
    if transition_duration <= 0:
        raise HTTPException(status_code=400, detail="Transition duration must be greater than zero")
    if fps <= 0:
        raise HTTPException(status_code=400, detail="FPS must be greater than zero")
    if zoom_peak < 1.0:
        raise HTTPException(status_code=400, detail="zoom_peak must be at least 1.0")

    clean_ingredients = [item.strip() for item in ingredients if item.strip()]
    if not clean_ingredients:
        raise HTTPException(status_code=400, detail="At least one ingredient is required")

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Invalid image content") from exc
    finally:
        if "image" in locals():
            image.close()

    cleaned_callback_url = validate_callback_url(callback_url) if callback_url.strip() else ""
    cleaned_callback_token = callback_bearer_token.strip()

    slug_name = slugified_filename(file.filename)
    stem = Path(slug_name).stem
    job_id = uuid4().hex
    status_url = build_absolute_url(str(request.base_url), f"/videos/recipe/jobs/{job_id}")
    source_path = job_dir(job_id) / f"source{detected_ext}"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(data)

    created_at = now_utc_iso()
    callback_state = {
        "url": cleaned_callback_url or None,
        "bearer_token": cleaned_callback_token or None,
        "status": "pending" if cleaned_callback_url else "disabled",
        "attempts": 0,
        "last_attempt_at": None,
        "next_attempt_at": None,
        "last_status_code": None,
        "last_error": None,
        "delivered_at": None,
    }

    payload = {
        "job_id": job_id,
        "status": "queued",
        "created_at": created_at,
        "updated_at": created_at,
        "base_url": str(request.base_url),
        "status_url": status_url,
        "source": {
            "path": str(source_path),
            "original_filename": file.filename,
            "slug_stem": stem,
        },
        "parameters": {
            "title": title,
            "subtitle": subtitle,
            "ingredients": clean_ingredients,
            "ingredients_title": ingredients_title,
            "brand": brand,
            "title_duration": title_duration,
            "ingredients_duration": ingredients_duration,
            "transition": transition,
            "transition_duration": transition_duration,
            "fps": fps,
            "zoom_peak": zoom_peak,
        },
        "result": None,
        "error": None,
        "callback": callback_state,
    }
    write_job_file(job_path(job_id), payload)
    logger.info(
        "Queued recipe video job job_id=%s title=%r callback_url=%s ingredients=%s",
        job_id,
        title,
        cleaned_callback_url or "-",
        len(clean_ingredients),
    )
    schedule_generation(job_id)
    return sanitize_job(payload)


def get_recipe_video_job(job_id: str) -> dict[str, Any]:
    return sanitize_job(load_job(job_id))
