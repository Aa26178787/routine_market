from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductForm
from .models import Category, ExerciseGoal, Product
from .services import save_product, suspend_product
from apps.orders.models import OrderItem
from apps.reviews.models import Review


def _verified_trainer(request):
    profile = getattr(request.user, "trainer_profile", None)
    if not profile or not profile.is_verified:
        raise PermissionDenied("승인된 트레이너만 접근할 수 있습니다.")
    return profile


def product_list(request):
    products = (
        Product.objects.filter(status=Product.Status.PUBLISHED)
        .select_related("seller__user", "category")
        .annotate(
            average_rating=Avg("reviews__rating", filter=Q(reviews__is_visible=True)),
            review_count=Count("reviews", filter=Q(reviews__is_visible=True), distinct=True),
        )
    )

    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    difficulty = request.GET.get("difficulty", "")
    goal = request.GET.get("goal", "")
    min_price = request.GET.get("min_price", "")
    max_price = request.GET.get("max_price", "")
    max_duration = request.GET.get("max_duration", "")
    sort = request.GET.get("sort", "latest")

    if query:
        products = products.filter(
            Q(title__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
        )
    if category:
        products = products.filter(category__slug=category)
    if difficulty in Product.Difficulty.values:
        products = products.filter(difficulty=difficulty)
    if goal:
        products = products.filter(goals__slug=goal)
    if min_price.isdigit():
        products = products.filter(price__gte=int(min_price))
    if max_price.isdigit():
        products = products.filter(price__lte=int(max_price))
    if max_duration.isdigit():
        products = products.filter(duration_weeks__lte=int(max_duration))

    ordering = {
        "latest": ("-published_at", "-created_at"),
        "price_low": ("price", "-created_at"),
        "price_high": ("-price", "-created_at"),
        "rating": ("-average_rating", "-review_count", "-created_at"),
    }
    products = products.distinct().order_by(*ordering.get(sort, ordering["latest"]))
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    if "page" in query_params:
        query_params.pop("page")

    return render(
        request,
        "products/product_list.html",
        {
            "products": page_obj,
            "page_obj": page_obj,
            "result_count": paginator.count,
            "query_string": query_params.urlencode(),
            "categories": Category.objects.filter(is_active=True),
            "goals": ExerciseGoal.objects.filter(is_active=True),
            "difficulties": Product.Difficulty.choices,
            "filters": request.GET,
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.filter(status=Product.Status.PUBLISHED)
        .select_related("seller__user", "category")
        .prefetch_related(
            "goals",
            Prefetch(
                "reviews",
                queryset=Review.objects.filter(is_visible=True).select_related("author"),
                to_attr="visible_reviews",
            ),
        )
        .annotate(
            average_rating=Avg("reviews__rating", filter=Q(reviews__is_visible=True)),
            review_count=Count("reviews", filter=Q(reviews__is_visible=True), distinct=True),
        ),
        slug=slug,
    )
    is_wished = False
    is_in_cart = False
    is_purchased = False
    if request.user.is_authenticated:
        is_wished = product.wishlist_items.filter(user=request.user).exists()
        is_in_cart = product.cart_items.filter(cart__user=request.user).exists()
        is_purchased = product.order_items.filter(
            order__buyer=request.user, order__status="PAID"
        ).exists()
    return render(
        request,
        "products/product_detail.html",
        {
            "product": product,
            "is_wished": is_wished,
            "is_in_cart": is_in_cart,
            "is_purchased": is_purchased,
        },
    )


@login_required
def wishlist(request):
    items = (
        request.user.wishlist_items.select_related(
            "product__seller__user", "product__category"
        )
        .filter(product__status=Product.Status.PUBLISHED)
        .order_by("-created_at")
    )
    return render(request, "products/wishlist.html", {"items": items})


@login_required
def wishlist_toggle(request, product_id):
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed

        return HttpResponseNotAllowed(["POST"])
    product = get_object_or_404(Product, pk=product_id, status=Product.Status.PUBLISHED)
    wishlist_item, created = product.wishlist_items.get_or_create(user=request.user)
    if created:
        messages.success(request, "찜 목록에 추가했습니다.")
    else:
        wishlist_item.delete()
        messages.success(request, "찜 목록에서 제거했습니다.")
    return redirect("products:detail", slug=product.slug)


@login_required
def seller_dashboard(request):
    trainer = _verified_trainer(request)
    paid_sales = (
        OrderItem.objects.filter(product=OuterRef("pk"), order__status="PAID")
        .values("product")
        .annotate(revenue=Sum("unit_price"))
        .values("revenue")
    )
    products = (
        trainer.products.select_related("category")
        .annotate(
            sales_count=Count(
                "order_items",
                filter=Q(order_items__order__status="PAID"),
                distinct=True,
            ),
            average_rating=Avg("reviews__rating", filter=Q(reviews__is_visible=True)),
            virtual_revenue=Coalesce(
                Subquery(paid_sales, output_field=IntegerField()),
                Value(0),
            ),
        )
        .order_by("-created_at")
    )
    return render(request, "products/seller_dashboard.html", {"products": products})


@login_required
def product_create(request):
    _verified_trainer(request)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            save_product(
                form=form,
                user=request.user,
                thumbnail_file=form.cleaned_data["thumbnail_file"],
                routine_file=form.cleaned_data["routine_file"],
            )
            messages.success(request, "상품이 등록되었습니다.")
            return redirect("products:seller_dashboard")
    else:
        form = ProductForm()
    return render(request, "products/product_form.html", {"form": form, "mode": "create"})


@login_required
def product_update(request, pk):
    trainer = _verified_trainer(request)
    product = get_object_or_404(Product, pk=pk, seller=trainer)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            save_product(
                form=form,
                user=request.user,
                thumbnail_file=form.cleaned_data.get("thumbnail_file"),
                routine_file=form.cleaned_data.get("routine_file"),
            )
            messages.success(request, "상품이 수정되었습니다.")
            return redirect("products:seller_dashboard")
    else:
        form = ProductForm(instance=product)
    return render(
        request,
        "products/product_form.html",
        {"form": form, "product": product, "mode": "update"},
    )


@login_required
def product_suspend(request, pk):
    if request.method != "POST":
        raise PermissionDenied("POST 요청만 허용됩니다.")
    suspend_product(product_id=pk, user=request.user)
    messages.success(request, "상품 판매를 중지했습니다.")
    return redirect("products:seller_dashboard")
