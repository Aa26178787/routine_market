from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


MAX_THUMBNAIL_SIZE = 5 * 1024 * 1024
MAX_ROUTINE_FILE_SIZE = 20 * 1024 * 1024
THUMBNAIL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
THUMBNAIL_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
XLSX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
}


def validate_thumbnail(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in THUMBNAIL_EXTENSIONS:
        raise ValidationError("썸네일은 JPG, PNG 또는 WEBP 파일만 사용할 수 있습니다.")
    if uploaded_file.size > MAX_THUMBNAIL_SIZE:
        raise ValidationError("썸네일은 5MB 이하여야 합니다.")
    if uploaded_file.content_type not in THUMBNAIL_CONTENT_TYPES:
        raise ValidationError("썸네일의 MIME 유형이 허용되지 않습니다.")
    try:
        image = Image.open(uploaded_file)
        image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("올바른 이미지 파일이 아닙니다.") from exc
    finally:
        uploaded_file.seek(0)


def validate_routine_file(uploaded_file):
    if Path(uploaded_file.name).suffix.lower() != ".xlsx":
        raise ValidationError("운동 루틴은 XLSX 파일만 업로드할 수 있습니다.")
    if uploaded_file.size > MAX_ROUTINE_FILE_SIZE:
        raise ValidationError("운동 루틴 파일은 20MB 이하여야 합니다.")
    if uploaded_file.content_type not in XLSX_CONTENT_TYPES:
        raise ValidationError("운동 루틴 파일의 MIME 유형이 허용되지 않습니다.")
    try:
        with ZipFile(uploaded_file) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ValidationError("올바른 XLSX 파일이 아닙니다.")
            if "xl/vbaProject.bin" in names:
                raise ValidationError("매크로가 포함된 파일은 업로드할 수 없습니다.")
    except BadZipFile as exc:
        raise ValidationError("올바른 XLSX 파일이 아닙니다.") from exc
    finally:
        uploaded_file.seek(0)
