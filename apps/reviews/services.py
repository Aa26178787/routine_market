from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.orders.models import Order, OrderItem

from .models import Review


@transaction.atomic
def create_verified_review(
    *, author: User, order_item_id: int, rating: int, content: str
) -> Review:
    order_item = (
        OrderItem.objects.select_for_update()
        .select_related("order", "product")
        .get(pk=order_item_id)
    )
    if order_item.order.buyer_id != author.pk:
        raise PermissionDenied("자신이 구매한 상품에만 리뷰를 작성할 수 있습니다.")
    if order_item.order.status != Order.Status.PAID:
        raise ValidationError("결제 완료된 상품에만 리뷰를 작성할 수 있습니다.")
    if Review.objects.filter(author=author, product=order_item.product).exists():
        raise ValidationError("같은 상품에는 리뷰를 한 번만 작성할 수 있습니다.")

    review = Review(
        author=author,
        product=order_item.product,
        order_item=order_item,
        rating=rating,
        content=content.strip(),
    )
    review.full_clean()
    review.save()
    return review


@transaction.atomic
def update_review(*, review_id: int, author: User, rating: int, content: str) -> Review:
    review = Review.objects.select_for_update().select_related("order_item__order").get(
        pk=review_id
    )
    if review.author_id != author.pk:
        raise PermissionDenied("자신의 리뷰만 수정할 수 있습니다.")
    review.rating = rating
    review.content = content.strip()
    review.full_clean()
    review.save(update_fields=["rating", "content", "updated_at"])
    return review


@transaction.atomic
def delete_review(*, review_id: int, author: User) -> None:
    review = Review.objects.select_for_update().get(pk=review_id)
    if review.author_id != author.pk:
        raise PermissionDenied("자신의 리뷰만 삭제할 수 있습니다.")
    review.delete()
