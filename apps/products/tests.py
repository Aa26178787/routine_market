import io
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.trainers.models import TrainerProfile

from .models import Category, ExerciseGoal, Product, ProductFile


def make_png_upload(name="thumbnail.png"):
    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (24, 24), color=(35, 107, 69)).save(stream, format="PNG")
    return SimpleUploadedFile(name, stream.getvalue(), content_type="image/png")


def make_xlsx_upload(name="routine.xlsx"):
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("xl/workbook.xml", "<workbook></workbook>")
    return SimpleUploadedFile(
        name,
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class ProductModelTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            email="seller@example.com",
            password="safe-test-password",
            full_name="판매자",
            nickname="seller",
            role=get_user_model().Role.TRAINER,
        )
        self.trainer = TrainerProfile.objects.create(
            user=user,
            specialty="보디빌딩",
            career_years=4,
            introduction="소개",
            is_verified=True,
            verified_at=timezone.now(),
        )
        self.category, _ = Category.objects.get_or_create(
            name="보디빌딩", defaults={"slug": "bodybuilding"}
        )
        self.product = Product.objects.create(
            seller=self.trainer,
            category=self.category,
            title="초급 근력 루틴",
            slug="beginner-strength",
            short_description="초급자를 위한 루틴",
            description="상세한 상품 설명",
            difficulty=Product.Difficulty.BEGINNER,
            duration_weeks=4,
            sessions_per_week=3,
            price=10000,
            thumbnail_object_key="thumbnails/product.png",
        )

    def test_only_one_current_file_per_product(self):
        ProductFile.objects.create(
            product=self.product,
            version=1,
            object_key="routines/v1.xlsx",
            original_filename="routine.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=100,
            checksum_sha256="a" * 64,
            is_current=True,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductFile.objects.create(
                product=self.product,
                version=2,
                object_key="routines/v2.xlsx",
                original_filename="routine-v2.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size_bytes=100,
                checksum_sha256="b" * 64,
                is_current=True,
            )


class ProductViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.member = user_model.objects.create_user(
            email="member@example.com",
            password="safe-test-password",
            full_name="일반회원",
            nickname="member",
        )
        self.seller_user = user_model.objects.create_user(
            email="verified@example.com",
            password="safe-test-password",
            full_name="승인 판매자",
            nickname="verified-seller",
            role=user_model.Role.TRAINER,
        )
        self.trainer = TrainerProfile.objects.create(
            user=self.seller_user,
            specialty="보디빌딩",
            career_years=5,
            introduction="전문 트레이너",
            is_verified=True,
            verified_at=timezone.now(),
        )
        self.category, _ = Category.objects.get_or_create(
            name="보디빌딩", defaults={"slug": "bodybuilding"}
        )
        self.goal, _ = ExerciseGoal.objects.get_or_create(
            name="근력 향상", defaults={"slug": "strength"}
        )

    def test_member_cannot_open_product_create(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse("products:create"))

        self.assertEqual(response.status_code, 403)

    def test_verified_trainer_can_create_published_product(self):
        self.client.force_login(self.seller_user)
        payload = {
            "title": "5x5 근력 프로그램",
            "short_description": "기초 근력을 만드는 8주 프로그램",
            "description": "주 3회 진행하는 근력 프로그램입니다.",
            "category": self.category.pk,
            "goals": [self.goal.pk],
            "difficulty": Product.Difficulty.BEGINNER,
            "duration_weeks": 8,
            "sessions_per_week": 3,
            "price": 12000,
            "status": Product.Status.PUBLISHED,
            "thumbnail_file": make_png_upload(),
            "routine_file": make_xlsx_upload(),
        }

        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("products:create"), payload)

        self.assertRedirects(response, reverse("products:seller_dashboard"))
        product = Product.objects.get(title="5x5 근력 프로그램")
        self.assertEqual(product.status, Product.Status.PUBLISHED)
        self.assertEqual(product.files.get().version, 1)
        self.assertTrue(product.goals.filter(pk=self.goal.pk).exists())

    def test_public_list_only_shows_published_matching_products(self):
        published = Product.objects.create(
            seller=self.trainer,
            category=self.category,
            title="공개 근력 루틴",
            slug="public-strength",
            short_description="검색 가능한 근력 루틴",
            description="설명",
            difficulty=Product.Difficulty.BEGINNER,
            duration_weeks=4,
            sessions_per_week=3,
            price=9000,
            thumbnail_object_key="product-thumbnails/test.png",
            status=Product.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        published.goals.add(self.goal)
        Product.objects.create(
            seller=self.trainer,
            category=self.category,
            title="비공개 루틴",
            slug="draft-routine",
            short_description="표시되지 않아야 함",
            description="설명",
            difficulty=Product.Difficulty.ADVANCED,
            duration_weeks=12,
            sessions_per_week=4,
            price=30000,
            thumbnail_object_key="product-thumbnails/draft.png",
            status=Product.Status.DRAFT,
        )

        response = self.client.get(
            reverse("products:list"),
            {"q": "근력", "difficulty": Product.Difficulty.BEGINNER},
        )

        self.assertContains(response, published.title)
        self.assertNotContains(response, "비공개 루틴")

    def test_member_can_toggle_wishlist(self):
        product = Product.objects.create(
            seller=self.trainer,
            category=self.category,
            title="찜 테스트 루틴",
            slug="wishlist-routine",
            short_description="찜 테스트",
            description="설명",
            difficulty=Product.Difficulty.BEGINNER,
            duration_weeks=4,
            sessions_per_week=3,
            price=9000,
            thumbnail_object_key="product-thumbnails/wishlist.png",
            status=Product.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        self.client.force_login(self.member)

        self.client.post(reverse("products:wishlist_toggle", args=[product.pk]))
        self.assertTrue(product.wishlist_items.filter(user=self.member).exists())

        self.client.post(reverse("products:wishlist_toggle", args=[product.pk]))
        self.assertFalse(product.wishlist_items.filter(user=self.member).exists())
