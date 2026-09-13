import io
import tempfile
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import Order, OrderItem
from apps.trainers.models import TrainerProfile

from .forms import ProductForm
from .models import Category, ExerciseGoal, Product, ProductFile
from .services import save_product


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

    def _update_form(self, product, *, routine_file):
        form = ProductForm(
            {
                "title": product.title,
                "short_description": product.short_description,
                "description": product.description,
                "category": product.category_id,
                "goals": [self.goal.pk],
                "difficulty": product.difficulty,
                "duration_weeks": product.duration_weeks,
                "sessions_per_week": product.sessions_per_week,
                "price": product.price,
                "status": Product.Status.DRAFT,
            },
            {"routine_file": routine_file},
            instance=product,
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_new_uploads_are_deleted_when_product_database_save_fails(self):
        form = ProductForm(
            {
                "title": "저장 실패 루틴",
                "short_description": "업로드 정리 테스트",
                "description": "설명",
                "category": self.category.pk,
                "goals": [self.goal.pk],
                "difficulty": Product.Difficulty.BEGINNER,
                "duration_weeks": 4,
                "sessions_per_week": 3,
                "price": 10000,
                "status": Product.Status.DRAFT,
            },
            {
                "thumbnail_file": make_png_upload(),
                "routine_file": make_xlsx_upload(),
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        with (
            patch("apps.products.services.save_thumbnail", return_value="new/thumb.png"),
            patch(
                "apps.products.services.save_routine_file",
                return_value={
                    "object_key": "new/routine.xlsx",
                    "original_filename": "routine.xlsx",
                    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "size_bytes": 100,
                    "checksum_sha256": "d" * 64,
                },
            ),
            patch("apps.products.services.Product.full_clean", side_effect=IntegrityError),
            patch("apps.products.services.delete_upload") as delete_upload,
        ):
            with self.assertRaises(IntegrityError):
                save_product(
                    form=form,
                    user=self.seller_user,
                    thumbnail_file=form.cleaned_data["thumbnail_file"],
                    routine_file=form.cleaned_data["routine_file"],
                )

        self.assertCountEqual(
            [call.args[0] for call in delete_upload.call_args_list],
            ["new/thumb.png", "new/routine.xlsx"],
        )
        self.assertFalse(Product.objects.filter(title="저장 실패 루틴").exists())

    def test_replaced_file_is_preserved_when_an_order_references_it(self):
        product = Product.objects.create(
            seller=self.trainer,
            category=self.category,
            title="구매 버전 보존 루틴",
            slug="preserve-purchased-version",
            short_description="구매 버전 보존",
            description="설명",
            difficulty=Product.Difficulty.BEGINNER,
            duration_weeks=4,
            sessions_per_week=3,
            price=10000,
            thumbnail_object_key="old/thumb.png",
        )
        old_file = ProductFile.objects.create(
            product=product,
            version=1,
            object_key="old/routine.xlsx",
            original_filename="old.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=100,
            checksum_sha256="a" * 64,
        )
        order = Order.objects.create(buyer=self.member, total_amount=product.price)
        OrderItem.objects.create(
            order=order,
            product=product,
            product_file=old_file,
            seller=self.trainer,
            product_title=product.title,
            seller_name=self.seller_user.nickname,
            unit_price=product.price,
        )
        form = self._update_form(product, routine_file=make_xlsx_upload("new.xlsx"))
        with (
            patch(
                "apps.products.services.save_routine_file",
                return_value={
                    "object_key": "new/routine.xlsx",
                    "original_filename": "new.xlsx",
                    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "size_bytes": 100,
                    "checksum_sha256": "b" * 64,
                },
            ),
            patch("apps.products.services.delete_upload") as delete_upload,
            self.captureOnCommitCallbacks(execute=True),
        ):
            save_product(form=form, user=self.seller_user, routine_file=form.cleaned_data["routine_file"])

        old_file.refresh_from_db()
        self.assertFalse(old_file.is_current)
        self.assertTrue(ProductFile.objects.filter(pk=old_file.pk).exists())
        delete_upload.assert_not_called()

    def test_replaced_unpurchased_file_is_removed_after_commit(self):
        product = Product.objects.create(
            seller=self.trainer,
            category=self.category,
            title="미구매 버전 정리 루틴",
            slug="cleanup-unpurchased-version",
            short_description="미구매 버전 정리",
            description="설명",
            difficulty=Product.Difficulty.BEGINNER,
            duration_weeks=4,
            sessions_per_week=3,
            price=10000,
            thumbnail_object_key="old/thumb.png",
        )
        old_file = ProductFile.objects.create(
            product=product,
            version=1,
            object_key="old/unpurchased.xlsx",
            original_filename="old.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=100,
            checksum_sha256="a" * 64,
        )
        form = self._update_form(product, routine_file=make_xlsx_upload("new.xlsx"))
        with (
            patch(
                "apps.products.services.save_routine_file",
                return_value={
                    "object_key": "new/routine.xlsx",
                    "original_filename": "new.xlsx",
                    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "size_bytes": 100,
                    "checksum_sha256": "b" * 64,
                },
            ),
            patch("apps.products.services.delete_upload", return_value=True) as delete_upload,
            self.captureOnCommitCallbacks(execute=True),
        ):
            save_product(form=form, user=self.seller_user, routine_file=form.cleaned_data["routine_file"])

        self.assertFalse(ProductFile.objects.filter(pk=old_file.pk).exists())
        delete_upload.assert_called_once_with("old/unpurchased.xlsx")

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

    def test_seller_dashboard_is_paginated_and_shows_totals(self):
        for index in range(11):
            Product.objects.create(
                seller=self.trainer,
                category=self.category,
                title=f"판매 상품 {index}",
                slug=f"seller-product-{index}",
                short_description="판매 관리 페이지네이션 테스트",
                description="설명",
                difficulty=Product.Difficulty.BEGINNER,
                duration_weeks=4,
                sessions_per_week=3,
                price=10000,
                thumbnail_object_key=f"product-thumbnails/{index}.png",
                status=Product.Status.DRAFT,
            )
        self.client.force_login(self.seller_user)

        first_page = self.client.get(reverse("products:seller_dashboard"))
        second_page = self.client.get(
            reverse("products:seller_dashboard"), {"page": 2}
        )

        self.assertEqual(len(first_page.context["products"]), 10)
        self.assertEqual(len(second_page.context["products"]), 1)
        self.assertEqual(first_page.context["product_count"], 11)
        self.assertEqual(first_page.context["total_revenue"], 0)
