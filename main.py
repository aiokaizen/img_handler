from fastapi import Depends, FastAPI, Form, UploadFile, File, HTTPException, Request
from config.settings import ALLOWED_MIME, UPLOAD_DIR
from api_functions.auth import require_token
from api_functions.images import process_image, upload_single_image, get_single_image
from api_functions.videos import create_recipe_video, get_single_video

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


@app.post("/images/process")
async def upload_and_process_image(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    subtitle: str = Form(""),
    position: str = Form("top"),
    theme: str = Form("warm_light"),
    title_align: str = Form("center"),
    brand: str = Form("nomadmouse.com"),
    _: None = Depends(require_token),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.content_type or file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Unsupported media type")

    return await process_image(
        request,
        file,
        title,
        subtitle,
        position=position,
        theme=theme,
        title_align=title_align,
        brand=brand,
    )


@app.post("/videos/recipe")
async def create_recipe_video_endpoint(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    subtitle: str = Form(""),
    ingredient: list[str] = Form(...),
    ingredients_title: str = Form("Ingredients"),
    brand: str = Form(""),
    title_duration: float = Form(10.0),
    ingredients_duration: float = Form(50.0),
    transition: str = Form("fade"),
    transition_duration: float = Form(1.0),
    fps: int = Form(30),
    zoom_peak: float = Form(1.08),
    _: None = Depends(require_token),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.content_type or file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Unsupported media type")

    return await create_recipe_video(
        request,
        file,
        title=title,
        subtitle=subtitle,
        ingredients=ingredient,
        ingredients_title=ingredients_title,
        brand=brand,
        title_duration=title_duration,
        ingredients_duration=ingredients_duration,
        transition=transition,
        transition_duration=transition_duration,
        fps=fps,
        zoom_peak=zoom_peak,
    )


@app.get("/videos/{filename}", name="get_video")
def get_video(filename: str, _: None = Depends(require_token)):
    return get_single_video(filename)
