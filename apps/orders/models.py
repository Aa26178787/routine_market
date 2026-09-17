import uuid

from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Cart(TimeStampedModel):
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="cart",
        verbose_name="회원",
    )

    class Meta:
        verbose_name = "장바구니"
        verbose_name_plural = "장바구니"

    def __str__(self):
        return f"{self.user.nickname}의 장바구니"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", verbose_name="장바구니"
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="상품",
    )
    created_at = models.DateTimeField("추가시각", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "장바구니 상품"
        verbose_name_plural = "장바구니 상품"
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="uniq_cart_product")
        ]

    def __str__(self):
        return f"{self.cart.user.nickname} - {self.product.title}"


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "결제 대기"
        PAID = "PAID", "결제 완료"
        CANCELLED = "CANCELLED", "취소"

    order_number = models.UUIDField("주문번호", default=uuid.uuid4, unique=True, editable=False)
    buyer = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="구매자",
    )
    status = models.CharField(
        "주문 상태", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    total_amount = models.PositiveIntegerField("총 주문금액", default=0)
    paid_at = models.DateTimeField("결제 완료시각", null=True, blank=True)
    cancelled_at = models.DateTimeField("취소시각", null=True, blank=True)
    payment_provider = models.CharField("결제 제공자", max_length=30, blank=True)
    payment_key = models.CharField(
        "외부 결제키", max_length=200, null=True, blank=True, unique=True
    )
    payment_method = models.CharField("결제수단", max_length=50, blank=True)
    payment_receipt_url = models.URLField("영수증 URL", max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "주문"
        verbose_name_plural = "주문"
        indexes = [
            models.Index(fields=["buyer", "created_at"]),
            models.Index(fields=["status", "paid_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="PAID") | Q(paid_at__isnull=False),
                name="paid_order_has_paid_at",
            ),
            models.CheckConstraint(
                condition=~Q(status="CANCELLED") | Q(cancelled_at__isnull=False),
                name="cancelled_order_has_cancelled_at",
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0), name="order_total_nonnegative"
            ),
        ]

    def __str__(self):
        return str(self.order_number)


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="items", verbose_name="주문"
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="상품",
    )
    product_file = models.ForeignKey(
        "products.ProductFile",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="구매 파일 버전",
    )
    seller = models.ForeignKey(
        "trainers.TrainerProfile",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="판매자",
    )
    product_title = models.CharField("상품명 스냅샷", max_length=200)
    seller_name = models.CharField("판매자명 스냅샷", max_length=100)
    unit_price = models.PositiveIntegerField("주문 당시 가격")
    created_at = models.DateTimeField("생성시각", auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "주문 상품"
        verbose_name_plural = "주문 상품"
        indexes = [models.Index(fields=["seller", "created_at"])]
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="uniq_order_product"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="order_item_price_nonnegative"
            ),
        ]

    def __str__(self):
        return f"{self.order.order_number} - {self.product_title}"


class DownloadLog(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="download_logs",
        verbose_name="회원",
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="download_logs",
        verbose_name="주문 상품",
    )
    ip_address = models.GenericIPAddressField("요청 IP", null=True, blank=True)
    user_agent = models.CharField("브라우저 정보", max_length=500, blank=True)
    created_at = models.DateTimeField("발급시각", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "다운로드 기록"
        verbose_name_plural = "다운로드 기록"
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self):
        return f"{self.user.nickname} - {self.order_item.product_title}"
