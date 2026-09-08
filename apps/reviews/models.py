from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Review(TimeStampedModel):
    author = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="reviews",
        verbose_name="작성자",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="reviews",
        verbose_name="상품",
    )
    order_item = models.OneToOneField(
        "orders.OrderItem",
        on_delete=models.PROTECT,
        related_name="review",
        verbose_name="구매 항목",
    )
    rating = models.PositiveSmallIntegerField("평점")
    content = models.TextField("리뷰 내용")
    is_visible = models.BooleanField("공개 여부", default=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "리뷰"
        verbose_name_plural = "리뷰"
        indexes = [models.Index(fields=["product", "is_visible"])]
        constraints = [
            models.UniqueConstraint(
                fields=["author", "product"], name="uniq_author_product_review"
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=1) & Q(rating__lte=5),
                name="review_rating_between_1_and_5",
            ),
        ]

    def clean(self):
        errors = {}
        if self.order_item_id:
            if self.order_item.order.buyer_id != self.author_id:
                errors["author"] = "구매자와 리뷰 작성자가 일치하지 않습니다."
            if self.order_item.product_id != self.product_id:
                errors["product"] = "구매 상품과 리뷰 상품이 일치하지 않습니다."
            if self.order_item.order.status != "PAID":
                errors["order_item"] = "결제 완료된 구매에만 리뷰를 작성할 수 있습니다."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.product.title} - {self.rating}점"
