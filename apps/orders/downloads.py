from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponseRedirect


def build_download_response(*, product_file):
    if settings.PRIVATE_FILE_DELIVERY == "redirect":
        url = default_storage.url(
            product_file.object_key,
            expire=settings.DOWNLOAD_URL_EXPIRES,
        )
        return HttpResponseRedirect(url)

    stream = default_storage.open(product_file.object_key, "rb")
    return FileResponse(
        stream,
        as_attachment=True,
        filename=product_file.original_filename,
        content_type=product_file.content_type,
    )
