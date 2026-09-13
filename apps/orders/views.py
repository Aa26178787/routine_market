import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from apps.products.models import Product

from .downloads import build_download_response
from .models import Cart, CartItem, DownloadLog, Order, OrderItem
from .services import cancel_pending_order, complete_virtual_payment, create_order_from_cart


logger = logging.getLogger(__name__)


def _purchased_product_ids(user):
    return OrderItem.objects.filter(
        order__buyer=user, order__status=Order.Status.PAID
    ).values_list("product_id", flat=True)


@login_required
def cart_detail(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = list(cart.items.select_related("product__seller__user", "product__category"))
    total_amount = sum(item.product.price for item in items)
    return render(
        request,
        "orders/cart.html",
        {"cart": cart, "items": items, "total_amount": total_amount},
    )


@login_required
def cart_add(request, product_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    product = get_object_or_404(Product, pk=product_id, status=Product.Status.PUBLISHED)
    if product.seller.user_id == request.user.pk:
        messages.error(request, "자신이 판매하는 상품은 장바구니에 담을 수 없습니다.")
        return redirect("products:detail", slug=product.slug)
    if _purchased_product_ids(request.user).filter(product_id=product.pk).exists():
        messages.info(request, "이미 구매한 상품입니다.")
        return redirect("orders:purchase_history")

    cart, _ = Cart.objects.get_or_create(user=request.user)
    _, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if created:
        messages.success(request, "상품을 장바구니에 담았습니다.")
    else:
        messages.info(request, "이미 장바구니에 있는 상품입니다.")
    if request.POST.get("proceed") == "checkout":
        return redirect("orders:checkout")
    return redirect("orders:cart")


@login_required
def cart_remove(request, product_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    CartItem.objects.filter(cart__user=request.user, product_id=product_id).delete()
    messages.success(request, "장바구니에서 상품을 제거했습니다.")
    return redirect("orders:cart")


@login_required
def checkout(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = list(cart.items.select_related("product__seller__user", "product__category"))
    total_amount = sum(item.product.price for item in items)

    if request.method == "POST":
        try:
            order = create_order_from_cart(buyer=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("orders:cart")
        return redirect("orders:detail", order_number=order.order_number)

    return render(
        request,
        "orders/checkout.html",
        {"items": items, "total_amount": total_amount},
    )


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.filter(buyer=request.user).prefetch_related("items__product"),
        order_number=order_number,
    )
    return render(request, "orders/order_detail.html", {"order": order})


@login_required
def pay_order(request, order_number):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    order = get_object_or_404(Order, order_number=order_number, buyer=request.user)
    try:
        complete_virtual_payment(order_id=order.pk, buyer=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "가상 결제가 완료되었습니다.")
    return redirect("orders:detail", order_number=order.order_number)


@login_required
def cancel_order(request, order_number):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    order = get_object_or_404(Order, order_number=order_number, buyer=request.user)
    try:
        cancel_pending_order(order_id=order.pk, buyer=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "주문을 취소하고 상품을 장바구니로 돌려놓았습니다.")
    return redirect("orders:detail", order_number=order.order_number)


@login_required
def purchase_history(request):
    orders_queryset = (
        Order.objects.filter(buyer=request.user, status=Order.Status.PAID)
        .prefetch_related("items__product", "items__product_file", "items__review")
        .order_by("-paid_at")
    )
    summary = orders_queryset.aggregate(total_spent=Sum("total_amount"))
    paginator = Paginator(orders_queryset, 6)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "orders/purchase_history.html",
        {
            "orders": page_obj,
            "page_obj": page_obj,
            "total_spent": summary["total_spent"] or 0,
        },
    )


@login_required
def download_order_item(request, order_item_id):
    order_item = get_object_or_404(
        OrderItem.objects.select_related("order", "product_file"),
        pk=order_item_id,
        order__buyer=request.user,
        order__status=Order.Status.PAID,
    )
    try:
        file_exists = default_storage.exists(order_item.product_file.object_key)
    except Exception:
        logger.exception("Failed to check a purchased routine download")
        file_exists = False
    if not file_exists:
        messages.error(
            request,
            "XLSX 파일을 불러올 수 없습니다. 잠시 후 다시 시도하거나 고객센터에 문의해 주세요.",
        )
        return redirect("orders:purchase_history")

    try:
        response = build_download_response(product_file=order_item.product_file)
    except Exception:
        logger.exception("Failed to prepare a purchased routine download")
        messages.error(
            request,
            "XLSX 파일을 불러올 수 없습니다. 잠시 후 다시 시도하거나 고객센터에 문의해 주세요.",
        )
        return redirect("orders:purchase_history")

    DownloadLog.objects.create(
        user=request.user,
        order_item=order_item,
        ip_address=request.META.get("REMOTE_ADDR") or None,
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
    )
    return response
