from fastapi import Depends, FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from typing import Optional
from config.settings import ALLOWED_MIME, UPLOAD_DIR
from api_functions.auth import require_token
from api_functions.images import upload_single_image, get_single_image

app = FastAPI()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/images/upload")
async def upload_image(request: Request, file: UploadFile = File(...), _: None = Depends(require_token)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.content_type or file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Unsupported media type")

    return await upload_single_image(request, file)


@app.get("/images/{filename}", name="get_image")
def get_image(filename: str, _: None = Depends(require_token)):
    return get_single_image(filename)
