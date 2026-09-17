from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.products.models import Product, ProductFile

from .models import Cart, CartItem, Order, OrderItem
from .toss_payments import TossPaymentsClient, TossPaymentsError


@transaction.atomic
def create_order_from_cart(*, buyer: User) -> Order:
    cart, _ = Cart.objects.select_for_update().get_or_create(user=buyer)
    cart_items = list(
        CartItem.objects.filter(cart=cart)
        .select_related("product__seller__user")
        .order_by("id")
    )
    if not cart_items:
        raise ValidationError("장바구니가 비어 있습니다.")

    product_ids = [item.product_id for item in cart_items]
    already_purchased = set(
        OrderItem.objects.filter(
            order__buyer=buyer,
            order__status=Order.Status.PAID,
            product_id__in=product_ids,
        ).values_list("product_id", flat=True)
    )
    if already_purchased:
        raise ValidationError("이미 구매한 상품은 다시 구매할 수 없습니다.")

    snapshots = []
    total_amount = 0
    for cart_item in cart_items:
        product = cart_item.product
        if product.status != Product.Status.PUBLISHED:
            raise ValidationError(f"현재 구매할 수 없는 상품입니다: {product.title}")
        if not product.seller.is_verified or not product.seller.user.is_active:
            raise ValidationError(f"현재 판매할 수 없는 상품입니다: {product.title}")
        if product.seller.user_id == buyer.pk:
            raise ValidationError("자신이 등록한 상품은 구매할 수 없습니다.")
        try:
            product_file = product.files.get(is_current=True)
        except ProductFile.DoesNotExist as exc:
            raise ValidationError(f"다운로드 파일이 없는 상품입니다: {product.title}") from exc

        total_amount += product.price
        snapshots.append((product, product_file))

    order = Order.objects.create(buyer=buyer, total_amount=total_amount)
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=product,
                product_file=product_file,
                seller=product.seller,
                product_title=product.title,
                seller_name=product.seller.user.nickname,
                unit_price=product.price,
            )
            for product, product_file in snapshots
        ]
    )
    CartItem.objects.filter(pk__in=[item.pk for item in cart_items]).delete()
    return order


@transaction.atomic
def complete_virtual_payment(*, order_id: int, buyer: User) -> Order:
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.buyer_id != buyer.pk:
        raise PermissionDenied("자신의 주문만 결제할 수 있습니다.")
    if order.status == Order.Status.PAID:
        return order
    if order.status != Order.Status.PENDING:
        raise ValidationError("결제 대기 주문만 결제할 수 있습니다.")

    order.status = Order.Status.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "paid_at", "updated_at"])

    purchased_product_ids = order.items.values_list("product_id", flat=True)
    CartItem.objects.filter(cart__user=buyer, product_id__in=purchased_product_ids).delete()
    return order


def confirm_toss_payment(
    *, order_id: int, buyer: User, payment_key: str, toss_order_id: str, amount: int
) -> Order:
    """서버에 저장한 주문과 인증 결과를 검증한 뒤 토스 결제를 승인합니다."""
    order = Order.objects.get(pk=order_id)
    if order.buyer_id != buyer.pk:
        raise PermissionDenied("자신의 주문만 결제할 수 있습니다.")
    if order.status == Order.Status.PAID:
        if order.payment_key == payment_key:
            return order
        raise ValidationError("이미 다른 결제로 완료된 주문입니다.")
    if order.status != Order.Status.PENDING:
        raise ValidationError("결제 대기 주문만 결제할 수 있습니다.")
    if toss_order_id != str(order.order_number):
        raise ValidationError("주문번호가 일치하지 않습니다.")
    if amount != order.total_amount:
        raise ValidationError("결제 금액이 주문 금액과 일치하지 않습니다.")
    if not payment_key or len(payment_key) > 200:
        raise ValidationError("유효하지 않은 결제 정보입니다.")

    payment = TossPaymentsClient().confirm(
        payment_key=payment_key,
        order_id=toss_order_id,
        amount=amount,
    )
    if (
        payment.get("status") != "DONE"
        or payment.get("orderId") != toss_order_id
        or payment.get("paymentKey") != payment_key
        or payment.get("totalAmount") != amount
    ):
        raise TossPaymentsError(
            "INVALID_PAYMENT_RESPONSE",
            "결제 승인 결과를 확인할 수 없습니다. 관리자에게 문의해 주세요.",
        )

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order_id)
        if locked_order.status == Order.Status.PAID:
            if locked_order.payment_key == payment_key:
                return locked_order
            raise ValidationError("이미 다른 결제로 완료된 주문입니다.")
        if locked_order.status != Order.Status.PENDING:
            raise ValidationError("결제 대기 주문만 결제할 수 있습니다.")

        receipt = payment.get("receipt") or {}
        locked_order.status = Order.Status.PAID
        locked_order.paid_at = timezone.now()
        locked_order.payment_provider = "TOSS_PAYMENTS"
        locked_order.payment_key = payment_key
        locked_order.payment_method = str(payment.get("method") or "")[:50]
        locked_order.payment_receipt_url = str(receipt.get("url") or "")[:500]
        locked_order.save(
            update_fields=[
                "status",
                "paid_at",
                "payment_provider",
                "payment_key",
                "payment_method",
                "payment_receipt_url",
                "updated_at",
            ]
        )
        purchased_product_ids = locked_order.items.values_list("product_id", flat=True)
        CartItem.objects.filter(
            cart__user=buyer, product_id__in=purchased_product_ids
        ).delete()
    return locked_order


def downloadable_order_items(*, user: User) -> QuerySet[OrderItem]:
    return OrderItem.objects.filter(
        order__buyer=user, order__status=Order.Status.PAID
    ).select_related("order", "product", "product_file")


def user_can_download(*, user: User, order_item: OrderItem) -> bool:
    return (
        user.is_authenticated
        and order_item.order.buyer_id == user.pk
        and order_item.order.status == Order.Status.PAID
    )


@transaction.atomic
def cancel_pending_order(*, order_id: int, buyer: User) -> Order:
    order = Order.objects.select_for_update().prefetch_related("items__product").get(pk=order_id)
    if order.buyer_id != buyer.pk:
        raise PermissionDenied("자신의 주문만 취소할 수 있습니다.")
    if order.status != Order.Status.PENDING:
        raise ValidationError("결제 대기 주문만 취소할 수 있습니다.")

    order.status = Order.Status.CANCELLED
    order.cancelled_at = timezone.now()
    order.save(update_fields=["status", "cancelled_at", "updated_at"])

    cart, _ = Cart.objects.get_or_create(user=buyer)
    for item in order.items.all():
        if item.product.status == Product.Status.PUBLISHED:
            CartItem.objects.get_or_create(cart=cart, product=item.product)
    return order
