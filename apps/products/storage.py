import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from django.core.files.storage import default_storage


logger = logging.getLogger(__name__)


def _save_upload(*, uploaded_file, prefix: str) -> tuple[str, str]:
    extension = Path(uploaded_file.name).suffix.lower()
    object_key = f"{prefix}/{uuid4().hex}{extension}"
    saved_key = default_storage.save(object_key, uploaded_file)
    return saved_key, Path(uploaded_file.name).name


def save_thumbnail(*, uploaded_file, trainer_id: int) -> str:
    object_key, _ = _save_upload(
        uploaded_file=uploaded_file,
        prefix=f"product-thumbnails/{trainer_id}",
    )
    return object_key


def save_detail_image(*, uploaded_file, product_id: int) -> tuple[str, str]:
    return _save_upload(
        uploaded_file=uploaded_file,
        prefix=f"product-detail-images/{product_id}",
    )


def save_routine_file(*, uploaded_file, product_id: int) -> dict:
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)

    object_key, original_filename = _save_upload(
        uploaded_file=uploaded_file,
        prefix=f"routine-files/{product_id}",
    )
    return {
        "object_key": object_key,
        "original_filename": original_filename,
        "content_type": uploaded_file.content_type,
        "size_bytes": uploaded_file.size,
        "checksum_sha256": digest.hexdigest(),
    }


def delete_upload(object_key: str) -> bool:
    """Best-effort cleanup for an object which is no longer referenced by the DB."""
    if not object_key:
        return True
    try:
        default_storage.delete(object_key)
        return True
    except Exception:
        # Cleanup must never mask the database error which prompted it. Storage
        # lifecycle rules can remove a rare orphan if the backend is unavailable.
        logger.exception("Failed to delete an unreferenced product upload")
        return False
