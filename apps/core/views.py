from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Avg, Count, Q
from apps.products.models import Category, Product
from apps.trainers.models import TrainerProfile


def home(request):
    products = Product.objects.filter(status=Product.Status.PUBLISHED).select_related(
        "seller__user", "category"
    ).annotate(
        average_rating=Avg("reviews__rating", filter=Q(reviews__is_visible=True)),
        review_count=Count("reviews", filter=Q(reviews__is_visible=True)),
    )
    return render(request, "core/home.html", {
        "latest_products": products.order_by("-published_at", "-created_at")[:8],
        "popular_products": products.order_by("-review_count", "-published_at")[:4],
        "categories": Category.objects.filter(is_active=True),
        "trainers": TrainerProfile.objects.filter(is_verified=True, user__is_active=True).select_related("user")[:4],
    })


def health(request):
    return JsonResponse({"status": "ok"})
