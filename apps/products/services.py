from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import Product, ProductFile
from .storage import save_routine_file, save_thumbnail


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


@transaction.atomic
def save_product(*, form, user, thumbnail_file=None, routine_file=None) -> Product:
    trainer = _assert_verified_trainer(user)
    product = form.save(commit=False)
    if product.pk and product.seller_id != trainer.pk:
        raise PermissionDenied("자신의 상품만 수정할 수 있습니다.")

    product.seller = trainer
    product.slug = _unique_slug(product.title, product_id=product.pk)
    if thumbnail_file:
        product.thumbnail_object_key = save_thumbnail(
            uploaded_file=thumbnail_file, trainer_id=trainer.pk
        )
    if not product.thumbnail_object_key:
        raise ValidationError("상품 썸네일이 필요합니다.")
    if product.status == Product.Status.PUBLISHED and not product.published_at:
        product.published_at = timezone.now()
    product.save()
    form.save_m2m()

    if routine_file:
        ProductFile.objects.filter(product=product, is_current=True).update(is_current=False)
        last_version = (
            ProductFile.objects.filter(product=product)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
            or 0
        )
        metadata = save_routine_file(uploaded_file=routine_file, product_id=product.pk)
        ProductFile.objects.create(
            product=product,
            version=last_version + 1,
            is_current=True,
            **metadata,
        )

    product.full_clean()
    product.save()
    return product


@transaction.atomic
def suspend_product(*, product_id: int, user) -> Product:
    trainer = _assert_verified_trainer(user)
    product = Product.objects.select_for_update().get(pk=product_id)
    if product.seller_id != trainer.pk:
        raise PermissionDenied("자신의 상품만 판매 중지할 수 있습니다.")
    product.status = Product.Status.SUSPENDED
    product.save(update_fields=["status", "updated_at"])
    return product
