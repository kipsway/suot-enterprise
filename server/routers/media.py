"""Загрузка медиафайлов (фото сотрудников, нарушений и т.д.)."""

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from server.deps import get_db, get_current_user
from app_core.config import RUNTIME_PATHS

router = APIRouter(prefix="/api/media", tags=["media"])

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_SIZE = 8 * 1024 * 1024  # 8 МБ


@router.post("/upload")
async def upload(file: UploadFile, db=Depends(get_db), user=Depends(get_current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            400, f"Только изображения: {', '.join(sorted(ALLOWED_EXT))}"
        )
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "Файл больше 8 МБ")
    if not data:
        raise HTTPException(400, "Пустой файл")

    name = f"{uuid.uuid4().hex}{ext}"
    media_dir = str(RUNTIME_PATHS.media_dir)
    os.makedirs(media_dir, exist_ok=True)
    with open(os.path.join(media_dir, name), "wb") as fh:
        fh.write(data)

    db.log_event(
        "Media uploaded",
        "INFO",
        {"user": user["username"], "file": name, "size": len(data)},
    )
    return {"url": f"/media/{name}", "size": len(data)}
