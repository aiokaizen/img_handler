# img_handler

A minimal image upload + retrieval API built with **FastAPI**, designed for simple deployments behind **Nginx** and managed by **systemd**.  
It supports:

- Uploading images via `multipart/form-data`
- Storing images on the server filesystem
- Returning a public URL to retrieve the stored image
- Preventing filename collisions by appending a UTC timestamp
- Simple authentication using a **static Bearer token** in the `Authorization` header
- Optional filename normalization (slugified filenames)

---

## API Overview

### 1) Upload an image
**Endpoint:** `POST /upload-image`  
**Auth:** Required (`Authorization: Bearer <token>`)  
**Body:** `multipart/form-data` with a `file` field.

**Behavior**
- Accepts common image types (JPEG/PNG/GIF/WebP).
- Saves the file to disk.
- If the filename already exists, it saves as `name_<timestamp>.<ext>`.
- Returns a JSON payload including the image URL.

**Response example**
```json
{
  "stored_as": "my-image_20260207T120102123456Z.png",
  "bytes": 54321,
  "image_url": "https://storage.pyzen.io/image/my-image_20260207T120102123456Z.png"
}
2) Retrieve an uploaded image
Endpoint: GET /image/{filename}
Auth: Required (Authorization: Bearer <token>)
Response: The stored image file.

Quick Start (Local Development)
Requirements
Python 3.11+ (3.12 works fine)

pip / venv

Install
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
Configure Auth Token
Set a static token in your environment:

export AUTH_TOKEN="dev-token-change-me"
Run
uvicorn main:app --reload --host 127.0.0.1 --port 8764
Using the API
Upload (curl)
curl -X POST "http://127.0.0.1:8764/upload-image" \
  -H "Authorization: Bearer dev-token-change-me" \
  -F "file=@/path/to/image.png"
Retrieve (curl)
curl -L \
  -H "Authorization: Bearer dev-token-change-me" \
  "http://127.0.0.1:8764/image/yourfile.png" \
  --output downloaded.png
Production Deployment (Nginx + systemd)
This repo is designed for:

Uvicorn bound to localhost:8764

Nginx serving storage.pyzen.io and proxying to the app

Provided configs
This repo includes:

img_handler.service (systemd unit)

storage.pyzen.io (nginx site config)

setup.sh (installer script)

One-shot setup
On the server:

sudo ./setup.sh
What it does:

Installs the Nginx site config and enables it

Restarts Nginx

Creates /etc/img_handler/img_handler.env with a random AUTH_TOKEN

Installs and starts the img_handler systemd service

Important: Ensure TLS certs exist at /etc/letsencrypt/live/storage.pyzen.io/... (or edit the nginx config accordingly).

Customization
1) Change upload directory
The upload directory is controlled by UPLOAD_DIR.

In systemd unit:

Environment="UPLOAD_DIR=/var/lib/img_handler/uploads"
In local dev, export it:

export UPLOAD_DIR="./uploads"
2) Increase max upload size
There are two limits to consider:

Application limit (MAX_BYTES in code)

Nginx limit (client_max_body_size in nginx config)

Update both if you increase file size limits.

3) Allowed image types
In code, adjust:

ALLOWED_MIME

The detection logic (magic bytes) if you add more types

4) Slugified filenames
If you want to store slugified filenames rather than raw user filenames, this project can use python-slugify.

Install:

pip install python-slugify
Then use slug logic in the upload handler (example approach):

take file.filename

slugify the basename (stem)

keep the extension

apply collision timestamping

5) Auth header format
Current auth expects:

Authorization: Bearer <token>

If you prefer an API key header (e.g. X-API-Key), update the dependency accordingly.

Notes and Security Considerations
This auth is intentionally simple: a shared static token suitable for internal use or low-risk APIs.

Store AUTH_TOKEN as a secret (systemd env file with mode 600).

Recommended systemd hardening is enabled (ProtectSystem=strict, ReadWritePaths=..., etc.).

Consider adding:

rate limiting (Nginx limit_req)

request logging / audit trail

object storage (S3/MinIO) if you need horizontal scaling

Repo Layout (suggested)
.
├── main.py
├── requirements.txt
├── img_handler.service
├── storage.pyzen.io
├── setup.sh
└── README.md
License
Add your preferred license (MIT/Apache-2.0/etc.) depending on how you plan to distribute this repository.