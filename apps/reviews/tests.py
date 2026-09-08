from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import Order, OrderItem
from apps.products.models import Category, Product, ProductFile
from apps.trainers.models import TrainerProfile

from .services import create_verified_review


class ReviewServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.buyer = user_model.objects.create_user(
            email="buyer@example.com",
            password="safe-test-password",
            full_name="구매자",
            nickname="buyer",
        )
        seller_user = user_model.objects.create_user(
            email="seller@example.com",
            password="safe-test-password",
            full_name="판매자",
            nickname="seller",
            role=user_model.Role.TRAINER,
        )
        trainer = TrainerProfile.objects.create(
            user=seller_user,
            specialty="홈트레이닝",
            career_years=2,
            introduction="홈트레이닝 코치",
            is_verified=True,
            verified_at=timezone.now(),
        )
        category, _ = Category.objects.get_or_create(
            name="홈트레이닝", defaults={"slug": "home-training"}
        )
        product = Product.objects.create(
            seller=trainer,
            category=category,
            title="홈트 루틴",
            slug="home-routine",
            short_description="집에서 하는 운동",
            description="상세 설명",
            difficulty=Product.Difficulty.BEGINNER,
            duration_weeks=4,
            sessions_per_week=3,
            price=5000,
            thumbnail_object_key="thumbnails/home.png",
            status=Product.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        product_file = ProductFile.objects.create(
            product=product,
            version=1,
            object_key="routines/home-v1.xlsx",
            original_filename="home.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=100,
            checksum_sha256="d" * 64,
            is_current=True,
        )
        order = Order.objects.create(
            buyer=self.buyer,
            status=Order.Status.PAID,
            total_amount=5000,
            paid_at=timezone.now(),
        )
        self.order_item = OrderItem.objects.create(
            order=order,
            product=product,
            product_file=product_file,
            seller=trainer,
            product_title=product.title,
            seller_name=trainer.user.nickname,
            unit_price=5000,
        )

    def test_paid_buyer_can_write_one_review(self):
        review = create_verified_review(
            author=self.buyer,
            order_item_id=self.order_item.pk,
            rating=5,
            content="좋은 프로그램입니다.",
        )

        self.assertEqual(review.rating, 5)
        with self.assertRaises(ValidationError):
            create_verified_review(
                author=self.buyer,
                order_item_id=self.order_item.pk,
                rating=4,
                content="두 번째 리뷰",
            )

    def test_review_create_update_delete_views(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("reviews:create", args=[self.order_item.pk]),
            {"rating": 5, "content": "실제로 따라유용하게 사용한 운동 프로그램입니다."},
        )
        review = self.order_item.review

        self.assertRedirects(
            response, reverse("products:detail", args=[self.order_item.product.slug])
        )
        self.assertEqual(review.rating, 5)

        response = self.client.post(
            reverse("reviews:update", args=[review.pk]),
            {"rating": 4, "content": "수정한 리뷰 내용도 충분히 길게 작성합니다."},
        )
        review.refresh_from_db()

        self.assertEqual(review.rating, 4)
        self.assertRedirects(
            response, reverse("products:detail", args=[self.order_item.product.slug])
        )

        response = self.client.post(reverse("reviews:delete", args=[review.pk]))

        self.assertRedirects(
            response, reverse("products:detail", args=[self.order_item.product.slug])
        )
        self.assertFalse(self.order_item.product.reviews.exists())
