from fastapi import APIRouter, UploadFile, File, Depends, Form

from app.core.config import Settings, settings
from app.core.exceptions import AppException
from app.core.responses import SuccessResponse
from app.domains.files.schemas.file_schemas import FileCategory
from app.domains.users.dependencies import get_current_user
from app.domains.users.models import User
from app.infrastructure.minio import minio_manager

router = APIRouter(prefix="/files", tags=["Files"])

MAX_FILE_SIZE = 1024 * 1024 * 50


@router.post("/upload", response_model=SuccessResponse[dict])
async def upload_file(file: UploadFile = File(...), category: FileCategory = Form(FileCategory.MESSAGE),
                      user: User = Depends(get_current_user)):
    target_bucket = (
        settings.MINIO_AVATAR_BUCKET
        if category == FileCategory.AVATAR
        else settings.MINIO_MESSAGE_BUCKET
    )

    file_bytes = await file.read()
    file_size = len(file_bytes)

    if file_size > MAX_FILE_SIZE:
        raise AppException(413, "FILE_SIZE_TOO_LARGE",
                           f"File size exceeds the maximum limit of {MAX_FILE_SIZE / (1024 * 1024)} MB.")

    filename = file.filename or "encrypted_file.enc"
    content_type = file.content_type or "application/octet-stream"

    file_url = await minio_manager.upload_file(
        file_bytes=file_bytes,
        original_filename=filename,
        content_type=content_type,
        bucket_name=target_bucket,
    )

    attachment_data = {
        "url": file_url,
        "name": filename,
        "size": file_size,
        "content_type": content_type,
    }

    return SuccessResponse(data=attachment_data)
