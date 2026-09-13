from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.models import Order, OrderItem

from .forms import ReviewForm
from .models import Review
from .services import create_verified_review, delete_review, update_review


@login_required
def review_create(request, order_item_id):
    order_item = get_object_or_404(
        OrderItem.objects.select_related("order", "product"),
        pk=order_item_id,
        order__buyer=request.user,
        order__status=Order.Status.PAID,
    )
    existing = Review.objects.filter(author=request.user, product=order_item.product).first()
    if existing:
        return redirect("reviews:update", pk=existing.pk)

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = create_verified_review(
                author=request.user,
                order_item_id=order_item.pk,
                rating=form.cleaned_data["rating"],
                content=form.cleaned_data["content"],
            )
            messages.success(request, "리뷰가 등록되었습니다.")
            return redirect("products:detail", slug=review.product.slug)
    else:
        form = ReviewForm()
    return render(
        request,
        "reviews/review_form.html",
        {"form": form, "order_item": order_item, "mode": "create",
         "other_reviews": Review.objects.filter(product=order_item.product, is_visible=True).select_related("author")[:10]},
    )


@login_required
def review_update(request, pk):
    review = get_object_or_404(
        Review.objects.select_related("product", "order_item"), pk=pk, author=request.user
    )
    if request.method == "POST":
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            review = update_review(
                review_id=review.pk,
                author=request.user,
                rating=form.cleaned_data["rating"],
                content=form.cleaned_data["content"],
            )
            messages.success(request, "리뷰가 수정되었습니다.")
            return redirect("products:detail", slug=review.product.slug)
    else:
        form = ReviewForm(instance=review)
    return render(
        request,
        "reviews/review_form.html",
        {"form": form, "order_item": review.order_item, "review": review, "mode": "update",
         "other_reviews": Review.objects.filter(product=review.product, is_visible=True).select_related("author")[:10]},
    )


@login_required
def review_delete(request, pk):
    review = get_object_or_404(Review.objects.select_related("product"), pk=pk, author=request.user)
    if request.method == "GET":
        return render(request, "reviews/review_confirm_delete.html", {"review": review})
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])
    product_slug = review.product.slug
    delete_review(review_id=review.pk, author=request.user)
    messages.success(request, "리뷰가 삭제되었습니다.")
    return redirect("products:detail", slug=product_slug)
