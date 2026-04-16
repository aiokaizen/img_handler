from fastapi import Depends, FastAPI, Form, UploadFile, File, HTTPException, Request, status
from config.settings import ALLOWED_MIME, UPLOAD_DIR
from api_functions.auth import require_token
from api_functions.effects_api import apply_frosted_glass_triptych
from api_functions.images import process_image, upload_single_image, get_single_image
from api_functions.video_jobs import (
    create_recipe_video_job,
    get_recipe_video_job,
    start_video_job_scheduler,
    stop_video_job_scheduler,
)
from api_functions.videos import get_single_video

app = FastAPI()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def startup_event():
    start_video_job_scheduler()


@app.on_event("shutdown")
def shutdown_event():
    stop_video_job_scheduler()


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


@app.post("/videos/recipe", status_code=status.HTTP_202_ACCEPTED)
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
    callback_url: str = Form(""),
    callback_bearer_token: str = Form(""),
    _: None = Depends(require_token),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.content_type or file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Unsupported media type")

    job = await create_recipe_video_job(
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
        callback_url=callback_url,
        callback_bearer_token=callback_bearer_token,
    )
    return job


@app.get("/videos/recipe/jobs/{job_id}", name="get_recipe_video_job")
def get_recipe_video_job_endpoint(job_id: str, _: None = Depends(require_token)):
    return get_recipe_video_job(job_id)


@app.get("/videos/{filename}", name="get_video")
def get_video(filename: str, _: None = Depends(require_token)):
    return get_single_video(filename)


@app.post("/images/effects/frosted_glass_triptych")
async def frosted_glass_triptych_endpoint(
    request: Request,
    file_top: UploadFile = File(...),
    file_bottom: UploadFile = File(...),
    title: str = Form(...),
    subtitle: str = Form(""),
    brand: str = Form(""),
    primary_hex: str = Form(""),
    secondary_hex: str = Form(""),
    tertiary_hex: str = Form(""),
    output_size: str = Form("pin_2x3"),
    _: None = Depends(require_token),
):
    for f in (file_top, file_bottom):
        if not f.filename:
            raise HTTPException(status_code=400, detail="Missing filename")
        if not f.content_type or f.content_type not in ALLOWED_MIME:
            raise HTTPException(status_code=415, detail="Unsupported media type")

    return await apply_frosted_glass_triptych(
        request,
        file_top,
        file_bottom,
        title=title,
        subtitle=subtitle,
        brand=brand,
        primary_hex=primary_hex,
        secondary_hex=secondary_hex,
        tertiary_hex=tertiary_hex,
        output_size=output_size,
    )
