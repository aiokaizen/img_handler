from fastapi import HTTPException
from fastapi.responses import FileResponse

from api_functions.images import safe_filename
from config.settings import UPLOAD_DIR


def get_single_video(filename: str):
    filename = safe_filename(filename)
    path = UPLOAD_DIR / filename

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(path)
