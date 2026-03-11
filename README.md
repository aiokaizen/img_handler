# img_handler

`img_handler` is a small FastAPI service that provides:

- authenticated image upload
- authenticated image retrieval
- authenticated image processing with a branded glassmorphism overlay
- filesystem-backed storage
- temporary signed public URLs for uploaded assets

It is designed to run behind Nginx and be managed by systemd. In the provided production configuration, Uvicorn listens on `127.0.0.1:8764` and Nginx proxies requests from `img_handler.com`.

## API

All application endpoints require:

```http
Authorization: Bearer <AUTH_TOKEN>
```

### `POST /images/upload`

Uploads an image from `multipart/form-data` using the `file` field.

Example:

```bash
curl -X POST "https://img_handler.com/images/upload" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -F "file=@/path/to/image.png"
```

Successful response:

```json
{
  "stored_filename": "my-image.png",
  "image_url": "https://img_handler.com/images/my-image.png",
  "public_url": "https://img_handler.com/images/public/my-image.png?md5=...&expires=...",
  "public_url_expiry": "11/03/2026 18:30"
}
```

Behavior:

- filenames are slugified before storage
- if a target filename already exists, a UTC timestamp is appended
- uploads are limited to `10 MB`
- only JPEG, PNG, WebP, and GIF are accepted

### `POST /images/process`

Accepts a source image and overlays a centered title/subtitle card plus branding. Required fields:

- `file`
- `title`

Optional fields:

- `subtitle`

Example:

```bash
curl -X POST "https://img_handler.com/images/process" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -F "file=@/path/to/image.png" \
  -F "title=Nomad Mouse" \
  -F "subtitle=Travel gear"
```

The processed image is stored as JPEG and returns the same response shape as `/images/upload`.

### `GET /images/{filename}`

Fetches a stored image through the authenticated app route.

Example:

```bash
curl -L \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  "https://img_handler.com/images/my-image.png" \
  --output downloaded.png
```

### `GET /images/public/{filename}`

This route is served directly by Nginx and does not use Bearer auth. Access is controlled by the signed `md5` and `expires` query parameters returned by the app.

## Configuration

Environment variables:

- `AUTH_TOKEN` (required): static Bearer token used by the FastAPI app
- `PUBLIC_LINK_SECRET` (required for signed public URLs): shared secret used by both FastAPI and Nginx
- `UPLOAD_DIR` (optional): directory where images are stored. Defaults to `/var/lib/img_handler/uploads`
- `PUBLIC_URL_TTL_SECONDS` (optional): signed public URL lifetime. Defaults to `864000` seconds (10 days)

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
uvicorn main:app --reload --host 127.0.0.1 --port 8764
```

Test upload:

```bash
curl -X POST "http://127.0.0.1:8764/images/upload" \
  -H "Authorization: Bearer dev-token-change-me" \
  -F "file=@/path/to/image.png"
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
