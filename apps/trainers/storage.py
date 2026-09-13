import logging
from pathlib import Path
from uuid import uuid4

from django.core.files.storage import default_storage


logger = logging.getLogger(__name__)


def save_certification_upload(*, uploaded_file, user_id: int) -> tuple[str, str]:
    extension = Path(uploaded_file.name).suffix.lower()
    object_key = f"trainer-certifications/{user_id}/{uuid4().hex}{extension}"
    saved_key = default_storage.save(object_key, uploaded_file)
    return saved_key, Path(uploaded_file.name).name


def delete_certification_upload(object_key: str) -> None:
    if not object_key:
        return
    try:
        default_storage.delete(object_key)
    except Exception:
        logger.exception("Failed to delete an unreferenced certification upload")
