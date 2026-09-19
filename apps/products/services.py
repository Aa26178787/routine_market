from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.text import slugify

from .models import Product, ProductDetailImage, ProductFile
from .storage import delete_upload, save_detail_image, save_routine_file, save_thumbnail


def _unique_slug(title: str, *, product_id: int | None = None) -> str:
    base_slug = slugify(title, allow_unicode=True)[:190] or "routine"
    candidate = base_slug
    suffix = 2
    queryset = Product.objects.exclude(pk=product_id)
    while queryset.filter(slug=candidate).exists():
        candidate = f"{base_slug}-{suffix}"
        suffix += 1
    return candidate


def _assert_verified_trainer(user):
    profile = getattr(user, "trainer_profile", None)
    if not profile or not profile.is_verified or not user.is_active:
        raise PermissionDenied("승인된 트레이너만 상품을 관리할 수 있습니다.")
    return profile


def save_product(
    *, form, user, thumbnail_file=None, routine_file=None, detail_images=None
) -> Product:
    uploaded_keys = []
    old_thumbnail_key = ""
    stale_file_ids = []
    try:
        with transaction.atomic():
            trainer = _assert_verified_trainer(user)
            product = form.save(commit=False)
            if product.pk:
                persisted = Product.objects.select_for_update().get(pk=product.pk)
                if persisted.seller_id != trainer.pk:
                    raise PermissionDenied("자신의 상품만 수정할 수 있습니다.")
                old_thumbnail_key = persisted.thumbnail_object_key

            product.seller = trainer
            product.slug = _unique_slug(product.title, product_id=product.pk)
            if thumbnail_file:
                product.thumbnail_object_key = save_thumbnail(
                    uploaded_file=thumbnail_file, trainer_id=trainer.pk
                )
                uploaded_keys.append(product.thumbnail_object_key)
            if not product.thumbnail_object_key:
                raise ValidationError("상품 썸네일이 필요합니다.")
            if product.status == Product.Status.PUBLISHED and not product.published_at:
                product.published_at = timezone.now()
            product.save()
            form.save_m2m()

            new_detail_images = list(detail_images or [])
            existing_detail_count = product.detail_images.count()
            if existing_detail_count + len(new_detail_images) > 5:
                raise ValidationError("상세 이미지는 상품당 최대 5장까지 등록할 수 있습니다.")
            for offset, detail_image in enumerate(new_detail_images):
                object_key, original_filename = save_detail_image(
                    uploaded_file=detail_image,
                    product_id=product.pk,
                )
                uploaded_keys.append(object_key)
                ProductDetailImage.objects.create(
                    product=product,
                    object_key=object_key,
                    original_filename=original_filename,
                    sort_order=existing_detail_count + offset,
                )

            if routine_file:
                stale_file_ids = list(
                    ProductFile.objects.filter(product=product, is_current=True)
                    .values_list("pk", flat=True)
                )
                ProductFile.objects.filter(pk__in=stale_file_ids).update(is_current=False)
                last_version = (
                    ProductFile.objects.filter(product=product)
                    .order_by("-version")
                    .values_list("version", flat=True)
                    .first()
                    or 0
                )
                metadata = save_routine_file(uploaded_file=routine_file, product_id=product.pk)
                uploaded_keys.append(metadata["object_key"])
                ProductFile.objects.create(
                    product=product,
                    version=last_version + 1,
                    is_current=True,
                    **metadata,
                )

            product.full_clean()
            product.save()

            if old_thumbnail_key and old_thumbnail_key != product.thumbnail_object_key:
                transaction.on_commit(lambda key=old_thumbnail_key: delete_upload(key))
            for stale_file_id in stale_file_ids:
                transaction.on_commit(
                    lambda file_id=stale_file_id: _delete_unpurchased_product_file(file_id)
                )
        return product
    except Exception:
        for object_key in uploaded_keys:
            delete_upload(object_key)
        raise


def _delete_unpurchased_product_file(product_file_id: int) -> None:
    """Remove an obsolete version only when no order snapshot references it."""
    with transaction.atomic():
        product_file = (
            ProductFile.objects.select_for_update()
            .filter(pk=product_file_id, is_current=False)
            .first()
        )
        if not product_file or product_file.order_items.exists():
            return
        object_key = product_file.object_key
        if delete_upload(object_key):
            try:
                product_file.delete()
            except ProtectedError:
                # An order created concurrently now owns this immutable file snapshot.
                return


@transaction.atomic
def suspend_product(*, product_id: int, user) -> Product:
    trainer = _assert_verified_trainer(user)
    product = Product.objects.select_for_update().get(pk=product_id)
    if product.seller_id != trainer.pk:
        raise PermissionDenied("자신의 상품만 판매 중지할 수 있습니다.")
    product.status = Product.Status.SUSPENDED
    product.save(update_fields=["status", "updated_at"])
    return product
