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

Creates a recipe video from a single image.

Default format:

- first 10 seconds: title + subtitle with zoom in
- next 50 seconds: ingredients with zoom out
- total duration: 60 seconds

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
  -F "brand="
```

Response:

```json
{
  "stored_filename": "chicken-katsu_recipe.mp4",
  "video_url": "http://127.0.0.1:8764/videos/chicken-katsu_recipe.mp4",
  "public_url": "http://127.0.0.1:8764/videos/public/chicken-katsu_recipe.mp4?md5=...&expires=...",
  "public_url_expiry": "27/03/2026 18:30",
  "transition": "fade"
}
```

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

- verify `PUBLIC_LINK_SECRET` matches between `/etc/img_handler/img_handler.env` and the rendered Nginx config
- `410` means the URL expired

### Service will not start

Inspect logs:

```bash
sudo journalctl -u img_handler -e --no-pager
```
