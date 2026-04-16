# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`img_handler` is a FastAPI service for food-blog media generation: authenticated image upload, editorial title-card image processing, and async recipe video generation. It runs behind Nginx with Uvicorn on `127.0.0.1:8764`, managed by systemd. Protected app routes use a static Bearer token; Nginx serves signed (`md5`+`expires`) temporary public URLs for media.

## Common commands

Local dev server:

```bash
source venv/bin/activate
export AUTH_TOKEN="dev-token-change-me"
export PUBLIC_LINK_SECRET="dev-public-link-secret"
export UPLOAD_DIR="/tmp/img_handler_uploads"
mkdir -p "$UPLOAD_DIR"
uvicorn main:app --reload --host 127.0.0.1 --port 8764
```

Install deps: `pip install -r requirements.txt`

Preview title-card positions/themes across a real image (hits the running server):

```bash
scripts/preview_positions.sh /absolute/path/to/image.jpg "Recipe Title" "Subtitle"
```

Generate a recipe video directly from the CLI (bypasses the API/job system):

```bash
python -m scripts.generate_recipe_tiktok_video <image> --title ... --ingredient ... [--transition fade|slide_up|wipe_left|zoom_cross|blur_fade]
```

Production install/reload (as root): `./system/setup.sh` — (re)renders Nginx config with `PUBLIC_LINK_SECRET`, writes `/etc/img_handler/img_handler.env`, installs the systemd unit. Service logs: `journalctl -u img_handler -e`.

There is no test suite and no linter configured.

## Architecture

### Request flow

`main.py` registers all FastAPI routes and on startup/shutdown hooks the video job scheduler. Every app endpoint depends on `api_functions/auth.py:require_token` which does a constant-time compare against `AUTH_TOKEN` from `config/settings.py`. Synchronous endpoints delegate to `api_functions/images.py` and `api_functions/videos.py`; the async video endpoint delegates to `api_functions/video_jobs.py`.

### Storage model

Everything lives under `UPLOAD_DIR` (default `/var/lib/img_handler/uploads`, overridable via env). Uploaded images, processed images, and finished videos all sit flat in that directory. Video job state lives in `UPLOAD_DIR/_video_jobs/<job_id>/` with `source.<ext>` plus a `job.json` that is the source of truth. Filenames are slugified on ingest; collisions get a UTC-microsecond suffix via `add_timestamp_if_exists`.

### Signed public URLs (critical invariant)

`make_public_url_from_base` in `api_functions/images.py` computes `md5(base64url("{expires}{uri} {PUBLIC_LINK_SECRET}"))`. The exact string format — `"$secure_link_expires$uri <secret>"` — MUST match the `secure_link_md5` directive in `system/img_handler.com`. If you change one, change the other. Nginx's `secure_link` module serves `/images/public/*` and `/videos/public/*` without hitting the app.

### Video job system (`api_functions/video_jobs.py`)

Async job pipeline, entirely file-based (no DB, no queue broker):

- `POST /videos/recipe` validates input, writes `job.json` with `status=queued`, returns `202` with `status_url`.
- On app startup a daemon `scheduler_loop` thread sweeps `VIDEO_JOBS_DIR/*/job.json` every `VIDEO_JOB_SWEEP_INTERVAL_SECONDS`. Any job in `{queued, processing}` is submitted to the `GENERATION_EXECUTOR` ThreadPool (`VIDEO_JOB_WORKERS` threads, default 1). This also picks up jobs left `processing` after a crash and resumes them.
- `process_recipe_video_job` flips status to `processing`, calls `scripts.generate_recipe_tiktok_video.generate_recipe_video`, writes the output to `UPLOAD_DIR`, then sets `completed` with a `result` dict or `failed` with `error.message` (and deletes the partial output).
- All state writes go through `mutate_job`, which takes `JOB_FILE_LOCK`, reads fresh from disk, applies the mutator, updates `updated_at`, and does an atomic `tmp+replace` write. Always mutate via `mutate_job` — do not write `job.json` directly.
- `ACTIVE_JOB_IDS` / `ACTIVE_CALLBACK_IDS` (guarded by `ACTIVE_LOCK`) prevent the sweeper from double-scheduling a job already running in-process.

Webhooks:

- If `callback_url` is provided, `CALLBACK_EXECUTOR` (single thread) `POST`s a JSON payload built by `build_callback_payload`. Optional `callback_bearer_token` becomes `Authorization: Bearer …`.
- Non-2xx or network errors trigger `mark_retry`: `status=retry_scheduled`, `next_attempt_at` = now + `compute_retry_delay_seconds(attempts)` (exponential, capped at 300s), up to `WEBHOOK_MAX_ATTEMPTS` (default 5). After max, `status=failed`.
- `sanitize_job` strips `bearer_token` before returning job state over the API — never leak it in responses or logs.

### Image processing (`api_functions/img_processing.py`)

`apply_title_layout` composes the editorial title card. `VALID_POSITIONS = {top, center, bottom}`, `VALID_THEMES = {warm_light, sage, mocha}`, `VALID_TITLE_ALIGNS = {center, left}`. Fonts are loaded from DejaVu paths under `/usr/share/fonts/truetype/dejavu/`; `load_font` falls back to PIL default if missing. `process_image` always re-encodes output as JPEG quality 92.

### Validation rules worth preserving

- `read_and_validate_image_upload` enforces: 10 MB max, MIME in `ALLOWED_MIME`, magic-byte sniff via `detect_image_ext`, and a check that the uploaded filename extension matches either the Content-Type or the sniffed type. Reuse this function for any new upload endpoint rather than re-implementing.
- `validate_callback_url` requires http/https scheme and a non-empty netloc.
- `safe_filename` strips path components — use it on anything filename-shaped that reaches the filesystem.

### Config (`config/settings.py`)

All runtime config is env-driven. Notable: `AUTH_TOKEN`, `PUBLIC_LINK_SECRET` (must match Nginx), `UPLOAD_DIR`, `VIDEO_JOBS_DIR`, `VIDEO_JOB_WORKERS`, `VIDEO_JOB_SWEEP_INTERVAL_SECONDS`, `WEBHOOK_TIMEOUT_SECONDS`, `WEBHOOK_MAX_ATTEMPTS`, `PUBLIC_URL_TTL_SECONDS` (default 10 days).

## Deployment notes

- systemd unit runs as `img_handler` user, `WorkingDirectory=/opt/img_handler`, venv at `/opt/img_handler/venv`. `ProtectSystem=strict` with only `/var/lib/img_handler/uploads` writable — new writable paths need a `ReadWritePaths` entry.
- Nginx `client_max_body_size 15m`; app caps at 10 MB — keep Nginx ≥ app so rejections happen inside the app with a proper JSON 413.
- Uvicorn runs with `--proxy-headers --forwarded-allow-ips 127.0.0.1` only; `request.base_url` is therefore trustworthy only when fronted by the local Nginx.
