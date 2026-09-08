from django.shortcuts import render

from apps.products.models import Product


def home(request):
    latest_products = (
        Product.objects.filter(status=Product.Status.PUBLISHED)
        .select_related("seller__user", "category")
        .order_by("-published_at", "-created_at")[:4]
    )
    return render(request, "core/home.html", {"latest_products": latest_products})
