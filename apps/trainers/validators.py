from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


MAX_CERTIFICATION_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_CERTIFICATION_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
ALLOWED_CERTIFICATION_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}


def validate_certification_file(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_CERTIFICATION_EXTENSIONS:
        raise ValidationError("자격 증빙은 JPG, PNG 또는 PDF 파일만 업로드할 수 있습니다.")
    if uploaded_file.size > MAX_CERTIFICATION_FILE_SIZE:
        raise ValidationError("자격 증빙 파일은 10MB 이하여야 합니다.")
    if uploaded_file.content_type not in ALLOWED_CERTIFICATION_CONTENT_TYPES:
        raise ValidationError("파일의 MIME 유형이 허용되지 않습니다.")

    try:
        if extension == ".pdf":
            if uploaded_file.read(5) != b"%PDF-":
                raise ValidationError("올바른 PDF 파일이 아닙니다.")
        else:
            image = Image.open(uploaded_file)
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("올바른 이미지 파일이 아닙니다.") from exc
    finally:
        uploaded_file.seek(0)
