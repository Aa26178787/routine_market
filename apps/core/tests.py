import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.views import defaults

from apps.orders.models import CartItem, Order
from apps.products.models import Product, ProductFile, WishlistItem
from apps.reviews.models import Review
from apps.trainers.models import TrainerApplication, TrainerProfile


@override_settings(
    DEBUG=True,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class SeedDemoCommandTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            call_command("seed_demo", verbosity=0)
            call_command("seed_demo", verbosity=0)
            call_command("seed_demo", reset=True, verbosity=0)

        user_model = get_user_model()
        self.assertEqual(
            user_model.objects.filter(email__endswith="@routine-market.local").count(),
            11,
        )
        self.assertEqual(TrainerApplication.objects.count(), 5)
        self.assertEqual(TrainerProfile.objects.count(), 4)
        self.assertEqual(Product.objects.filter(slug__startswith="demo-").count(), 8)
        self.assertEqual(ProductFile.objects.count(), 8)
        self.assertEqual(Order.objects.filter(status=Order.Status.PAID).count(), 17)
        self.assertEqual(Review.objects.count(), 17)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(WishlistItem.objects.count(), 1)


class ErrorPageTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/error-test/")

    def test_permission_denied_uses_custom_page(self):
        response = defaults.permission_denied(
            self.request,
            PermissionDenied("테스트 접근 거부"),
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("접근 권한이 없습니다", response.content.decode())

    def test_page_not_found_uses_custom_page(self):
        response = defaults.page_not_found(self.request, Exception("not found"))

        self.assertEqual(response.status_code, 404)
        self.assertIn("페이지를 찾을 수 없습니다", response.content.decode())

    def test_server_error_uses_custom_page(self):
        response = defaults.server_error(self.request)

        self.assertEqual(response.status_code, 500)
        self.assertIn("서비스 처리 중 문제가 발생했습니다", response.content.decode())


class HealthCheckTests(TestCase):
    def test_health_endpoint(self):
        response = self.client.get(reverse("core:health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
