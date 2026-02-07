# img_handler

`img_handler` is a small **FastAPI** service that provides:

- **Image upload** via `multipart/form-data`
- **Filesystem storage** of uploaded images
- **Image retrieval** over HTTP
- Filename collision handling: keeps the original name, and if it already exists, appends a **UTC timestamp**
- Simple authentication using a **static Bearer token** (`Authorization: Bearer <token>`)

It is designed to run behind **Nginx** and be managed by **systemd**. In the provided production configuration, Uvicorn listens on **127.0.0.1:8764** and Nginx exposes the service at **storage.pyzen.io**.

---

## API

### Authentication
All endpoints require:

```
Authorization: Bearer <AUTH_TOKEN>
```

`AUTH_TOKEN` is provided via environment variable (typically from `/etc/img_handler/img_handler.env` in production).

---

### Upload an image
**POST** `/upload-image`  
**Content-Type**: `multipart/form-data`  
**Field**: `file`

Example:
```bash
curl -X POST "https://storage.pyzen.io/upload-image" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -F "file=@/path/to/image.png"
```

Response (example):
```json
{
  "stored_as": "image_20260207T120102123456Z.png",
  "bytes": 54321,
  "image_url": "https://storage.pyzen.io/image/image_20260207T120102123456Z.png"
}
```

Behavior:
- If the filename does not exist yet, it is stored as-is.
- If the filename already exists, it is stored as `<stem>_<timestamp><ext>`.

---

### Retrieve an image
**GET** `/image/{filename}`

Example:
```bash
curl -L \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  "https://storage.pyzen.io/image/image.png" \
  --output downloaded.png
```

---

## Configuration

### Environment variables
- `AUTH_TOKEN` (**required**)  
  Static Bearer token used for authentication.
- `UPLOAD_DIR` (optional but recommended)  
  Filesystem directory where images are stored. In the systemd unit, it is typically set to:
  - `/var/lib/img_handler/uploads`

---

## Local development

### Install
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run
```bash
export AUTH_TOKEN="dev-token-change-me"
uvicorn main:app --reload --host 127.0.0.1 --port 8764
```

Test upload:
```bash
curl -X POST "http://127.0.0.1:8764/upload-image" \
  -H "Authorization: Bearer dev-token-change-me" \
  -F "file=@/path/to/image.png"
```

---

## Production deployment (systemd + Nginx)

This repository includes:
- `img_handler.service` (systemd unit)
- `storage.pyzen.io` (nginx site config)
- `setup.sh` (installs configs, generates token env file, starts the service)

### What `setup.sh` does
When executed as root, `setup.sh`:

1. Copies `storage.pyzen.io` to:
   - `/etc/nginx/sites-available/storage.pyzen.io`
2. Creates/updates a symlink:
   - `/etc/nginx/sites-enabled/storage.pyzen.io`
3. Tests and restarts Nginx
4. Creates:
   - `/etc/img_handler/img_handler.env`
   with a randomly generated `AUTH_TOKEN`
5. Copies `img_handler.service` to:
   - `/etc/systemd/system/img_handler.service`
6. Runs:
   - `systemctl daemon-reload`
   - `systemctl enable --now img_handler`

Run:
```bash
sudo ./setup.sh
```

### Assumptions in the provided configs
- Uvicorn runs on **127.0.0.1:8764**
- Nginx proxies to `http://127.0.0.1:8764`
- TLS certificate paths in the Nginx config use Let’s Encrypt defaults:
  - `/etc/letsencrypt/live/storage.pyzen.io/fullchain.pem`
  - `/etc/letsencrypt/live/storage.pyzen.io/privkey.pem`
- The systemd unit sets:
  - `UPLOAD_DIR=/var/lib/img_handler/uploads`

---

## Customization

### Change the domain
Edit `storage.pyzen.io`:
- Update `server_name`
- Update certificate paths for your domain

### Change the internal port
Update both:
- systemd `ExecStart ... --port <PORT>`
- nginx `proxy_pass http://127.0.0.1:<PORT>;`

### Change upload directory
Update the systemd unit:
```ini
Environment="UPLOAD_DIR=/var/lib/img_handler/uploads"
```

### Increase maximum upload size
Update both:
- Nginx `client_max_body_size`
- Application limit in code (e.g. `MAX_BYTES`) if you enforce one

---

## Optional: slugified filenames

If you want stored filenames to be a slug (instead of the original filename), use `python-slugify`:

1) Add to `requirements.txt`:
```txt
python-slugify>=8.0.0
```

2) In upload logic:
- slugify the filename stem
- keep the extension
- still append timestamp if it already exists

---

## Troubleshooting

### 401 Unauthorized
- Ensure the header is exactly:
  `Authorization: Bearer <token>`
- Verify `AUTH_TOKEN` on the server:
  - `/etc/img_handler/img_handler.env`

### Nginx 413 Request Entity Too Large
- Increase `client_max_body_size` in the Nginx config and reload.

### Service won’t start
Inspect logs:
```bash
sudo journalctl -u img_handler -e --no-pager
```

---

## Suggested repository structure
```
.
├── main.py
├── requirements.txt
├── img_handler.service
├── storage.pyzen.io
├── setup.sh
└── README.py
```