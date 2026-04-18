# img_handler

`img_handler` is a small FastAPI service for food-blog media generation. It currently supports:

- authenticated image upload
- authenticated image processing with an editorial title card
- authenticated recipe video generation from a single image
- authenticated image and video retrieval
- temporary signed public URLs for uploaded media

It is designed to run behind Nginx and be managed by systemd. In the provided production configuration, Uvicorn listens on `127.0.0.1:8764` and Nginx proxies requests from `img_handler.com`.

## Authentication

Every app endpoint uses a simple static Bearer token.

Header format:

```http
Authorization: Bearer <AUTH_TOKEN>
```

In local development you can set:

```bash
export AUTH_TOKEN="dev-token-change-me"
```

In production the token is typically stored in:

```text
/etc/img_handler/img_handler.env
```

## API

### `POST /images/upload`

Uploads an image from `multipart/form-data` using the `file` field.

```bash
curl -X POST "http://127.0.0.1:8764/images/upload" \
  -H "Authorization: Bearer dev-token-change-me" \
  -F "file=@/absolute/path/to/image.jpg"
```

Response:

```json
{
  "stored_filename": "my-image.jpg",
  "image_url": "http://127.0.0.1:8764/images/my-image.jpg",
  "public_url": "http://127.0.0.1:8764/images/public/my-image.jpg?md5=...&expires=...",
  "public_url_expiry": "27/03/2026 18:30"
}
```

### `POST /images/process`

Creates a processed food image with the editorial title card.

Optional fields:

- `subtitle`
- `position`: `top`, `center`, or `bottom`
- `theme`: `warm_light`, `sage`, or `mocha`
- `title_align`: `center` or `left`
- `brand`: custom branding text. Pass an empty string to omit it.

```bash
curl -X POST "http://127.0.0.1:8764/images/process" \
  -H "Authorization: Bearer dev-token-change-me" \
  -F "file=@/absolute/path/to/image.jpg" \
  -F "title=Brown Butter Banana Bread" \
  -F "subtitle=Soft, moist, and easy to make" \
  -F "position=top" \
  -F "theme=warm_light" \
  -F "title_align=center" \
  -F "brand=example.com"
```

### `POST /videos/recipe`

Creates a recipe video job from a single image.

Default format:

- first 10 seconds: title + subtitle with zoom in
- next 50 seconds: ingredients with zoom out
- total duration: 60 seconds

This endpoint is asynchronous. It returns `202 Accepted` immediately with a `job_id` and `status_url`.
The client can either poll the job status or provide a webhook callback URL.

Required fields:

- `file`
- `title`
- at least one `ingredient`

Optional fields:

- `subtitle`
- `ingredients_title`
- `brand`
- `title_duration`
- `ingredients_duration`
- `transition`: `fade`, `slide_up`, `wipe_left`, `zoom_cross`, `blur_fade`
- `transition_duration`
- `fps`
- `zoom_peak`
- `callback_url`: optional `http` or `https` endpoint that will receive completion events
- `callback_bearer_token`: optional static bearer token sent to the callback endpoint

Example:

```bash
curl -X POST "http://127.0.0.1:8764/videos/recipe" \
  -H "Authorization: Bearer dev-token-change-me" \
  -F "file=@/absolute/path/to/chicken_katsu.jpg" \
  -F "title=Chicken Katsu" \
  -F "subtitle=Crispy cutlet with cabbage and sauce" \
  -F "ingredient=4 chicken cutlets" \
  -F "ingredient=1 cup panko breadcrumbs" \
  -F "ingredient=2 eggs" \
  -F "ingredient=1/2 cup flour" \
  -F "ingredient=Oil for frying" \
  -F "ingredient=Tonkatsu sauce" \
  -F "ingredients_title=Ingredients" \
  -F "title_duration=10" \
  -F "ingredients_duration=50" \
  -F "transition=fade" \
  -F "transition_duration=1.0" \
  -F "callback_url=https://example.com/hooks/img-handler" \
  -F "callback_bearer_token=callback-secret-token" \
  -F "brand="
```

Response:

```json
{
  "job_id": "e7e747b1f59745f8b2140f5b4f598de4",
  "status": "queued",
  "created_at": "2026-03-27T14:15:11.273968+00:00",
  "updated_at": "2026-03-27T14:15:11.273968+00:00",
  "status_url": "http://127.0.0.1:8764/videos/recipe/jobs/e7e747b1f59745f8b2140f5b4f598de4",
  "result": null,
  "error": null,
  "callback": {
    "url": "https://example.com/hooks/img-handler",
    "status": "pending",
    "attempts": 0,
    "last_attempt_at": null,
    "next_attempt_at": null,
    "last_status_code": null,
    "last_error": null,
    "delivered_at": null
  }
}
```

### `GET /videos/recipe/jobs/{job_id}`

Fetches the current state of a recipe video job.

Statuses:

- `queued`
- `processing`
- `completed`
- `failed`

Example response after completion:

```json
{
  "job_id": "e7e747b1f59745f8b2140f5b4f598de4",
  "status": "completed",
  "created_at": "2026-03-27T14:15:11.273968+00:00",
  "updated_at": "2026-03-27T14:16:05.441829+00:00",
  "status_url": "http://127.0.0.1:8764/videos/recipe/jobs/e7e747b1f59745f8b2140f5b4f598de4",
  "result": {
    "stored_filename": "chicken-katsu_recipe.mp4",
    "video_url": "http://127.0.0.1:8764/videos/chicken-katsu_recipe.mp4",
    "public_url": "http://127.0.0.1:8764/videos/public/chicken-katsu_recipe.mp4?md5=...&expires=...",
    "public_url_expiry": "27/03/2026 18:30",
    "transition": "fade"
  },
  "error": null,
  "callback": {
    "url": "https://example.com/hooks/img-handler",
    "status": "delivered",
    "attempts": 1,
    "last_attempt_at": "2026-03-27T14:16:05.664391+00:00",
    "next_attempt_at": null,
    "last_status_code": 200,
    "last_error": null,
    "delivered_at": "2026-03-27T14:16:05.664391+00:00"
  }
}
```

### Recipe video webhook payload

When `callback_url` is provided, the service sends an authenticated `POST` with `Content-Type: application/json`.
If `callback_bearer_token` is set, the request includes:

```http
Authorization: Bearer <callback_bearer_token>
```

The webhook body looks like this:

```json
{
  "event": "video.recipe.completed",
  "job_id": "e7e747b1f59745f8b2140f5b4f598de4",
  "status": "completed",
  "created_at": "2026-03-27T14:15:11.273968+00:00",
  "updated_at": "2026-03-27T14:16:05.441829+00:00",
  "status_url": "http://127.0.0.1:8764/videos/recipe/jobs/e7e747b1f59745f8b2140f5b4f598de4",
  "result": {
    "stored_filename": "chicken-katsu_recipe.mp4",
    "video_url": "http://127.0.0.1:8764/videos/chicken-katsu_recipe.mp4",
    "public_url": "http://127.0.0.1:8764/videos/public/chicken-katsu_recipe.mp4?md5=...&expires=...",
    "public_url_expiry": "27/03/2026 18:30",
    "transition": "fade"
  },
  "error": null
}
```

If callback delivery fails, the service retries with backoff and keeps the retry state on the job record.

### `GET /images/{filename}`

Fetches a stored image through the authenticated app route.

```bash
curl -L \
  -H "Authorization: Bearer dev-token-change-me" \
  "http://127.0.0.1:8764/images/my-image.jpg" \
  --output downloaded.jpg
```

### `GET /videos/{filename}`

Fetches a stored video through the authenticated app route.

```bash
curl -L \
  -H "Authorization: Bearer dev-token-change-me" \
  "http://127.0.0.1:8764/videos/chicken-katsu_recipe.mp4" \
  --output recipe-video.mp4
```

### Public media URLs

These are served by Nginx and do not use Bearer auth:

- `GET /images/public/{filename}`
- `GET /videos/public/{filename}`

They are controlled by signed `md5` and `expires` query parameters returned by the app.

## Validation and limits

- uploads are limited to `10 MB`
- only JPEG, PNG, WebP, and GIF are accepted as source images
- filenames are slugified before storage
- if a target filename already exists, a UTC timestamp is appended

## Local development

Install:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run:

```bash
export AUTH_TOKEN="dev-token-change-me"
export PUBLIC_LINK_SECRET="dev-public-link-secret"
export UPLOAD_DIR="/tmp/img_handler_uploads"

mkdir -p "$UPLOAD_DIR"

uvicorn main:app --reload --host 127.0.0.1 --port 8764
```

## Production deployment

This repository includes:

- `system/img_handler.service`
- `system/img_handler.com`
- `system/setup.sh`

`system/setup.sh`:

1. creates or preserves `AUTH_TOKEN` and `PUBLIC_LINK_SECRET` in `/etc/img_handler/img_handler.env`
2. renders the Nginx config template with the shared public-link secret
3. installs and reloads Nginx
4. installs and starts the systemd service

Run:

```bash
sudo ./system/setup.sh
```

## Operational notes

- The service trusts proxy headers from local Nginx only
- `client_max_body_size` in Nginx is set to `15m`
- the app enforces its own `10 MB` payload cap
- signed public URLs are intended for temporary sharing, not permanent public hosting
- `position=top` is the default image title-card placement for bright recipe images with usable top negative space

## Troubleshooting

### `401 Unauthorized`

- ensure the header is exactly `Authorization: Bearer <token>`
- verify `AUTH_TOKEN` in `/etc/img_handler/img_handler.env`

### Signed public URLs return `403` or `410`

- `403` usually means the signed URL is invalid or `PUBLIC_LINK_SECRET` differs between the app and Nginx
- `410` means the URL expired and you need to generate a fresh one

### Signed public URLs return `404`

- first verify the authenticated route works:
  - `GET /images/{filename}` for images
  - `GET /videos/{filename}` for videos
- if the authenticated route works but the signed public URL returns `404`, check filesystem permissions for Nginx
- the production unit file sets `StateDirectoryMode=0755` so Nginx can traverse `/var/lib/img_handler` and read files from `/var/lib/img_handler/uploads`
- after updating the service file, run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart img_handler
```

- if needed, verify the live directory modes:

```bash
namei -om /var/lib/img_handler/uploads
```

- verify `PUBLIC_LINK_SECRET` matches between `/etc/img_handler/img_handler.env` and the rendered Nginx config
- `410` means the URL expired

### Service will not start

Inspect logs:

```bash
sudo journalctl -u img_handler -e --no-pager
```
