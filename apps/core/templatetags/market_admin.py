from django import template
from apps.accounts.models import User
from apps.products.models import Product
from apps.orders.models import Order
from apps.trainers.models import TrainerApplication

register = template.Library()


@register.simple_tag(takes_context=True)
def market_dashboard(context):
    user = context["request"].user
    data = {"metrics": []}
    if not user.is_active or not user.is_staff:
        return data
    for permission, model, label in (
        ("accounts.view_user", User, "총 회원 수"),
        ("trainers.view_trainerapplication", TrainerApplication, "승인 대기"),
        ("products.view_product", Product, "등록 상품 수"),
        ("orders.view_order", Order, "총 주문 수"),
    ):
        if user.has_perm(permission):
            queryset = model.objects.all()
            if model is TrainerApplication:
                queryset = queryset.filter(status="PENDING")
                data["applications"] = queryset.select_related("user")[:5]
            data["metrics"].append({"label": label, "count": queryset.count()})
    if user.has_perm("orders.view_order"):
        data["orders"] = Order.objects.select_related("buyer").order_by("-created_at")[:6]
    return data
