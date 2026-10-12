from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse

from apps.core.templatetags.market import won
from apps.core.templatetags.market_admin import market_dashboard


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DesignIntegrationTests(TestCase):
    def test_public_pages_render_shared_design(self):
        for name in ("core:home", "products:list", "accounts:login", "accounts:signup"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "market.css")
                self.assertContains(response, 'aria-label="운동 루틴 검색"')

    def test_dashboard_metrics_respect_model_permissions(self):
        user = get_user_model().objects.create_user(
            email="limited-admin@example.com", password="test-password",
            nickname="제한 관리자", full_name="관리자", is_staff=True,
        )
        request = RequestFactory().get("/admin/")
        request.user = user
        self.assertEqual(market_dashboard({"request": request})["metrics"], [])
        user.user_permissions.add(Permission.objects.get(content_type__app_label="products", codename="view_product"))
        request.user = get_user_model().objects.get(pk=user.pk)
        data = market_dashboard({"request": request})
        self.assertEqual([item["label"] for item in data["metrics"]], ["등록 상품 수"])
        self.assertNotIn("applications", data)
        self.assertNotIn("orders", data)

    def test_won_format(self):
        self.assertEqual(won(39000), "₩39,000")
        self.assertEqual(won(0), "₩0")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SessionIsolationTests(TestCase):
    def setUp(self):
        self.member = get_user_model().objects.create_user(
            email="member-session@example.com",
            password="Member-session1!",
            nickname="일반 세션",
            full_name="일반 회원",
        )
        self.admin = get_user_model().objects.create_superuser(
            email="admin-session@example.com",
            password="Admin-session1!",
            nickname="관리자 세션",
            full_name="관리자",
        )

    def test_admin_login_does_not_authenticate_storefront(self):
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": self.admin.email,
                "password": "Admin-session1!",
                "next": reverse("admin:index"),
            },
        )

        self.assertRedirects(response, reverse("admin:index"))
        self.assertIn("admin_sessionid", self.client.cookies)
        storefront = self.client.get(reverse("core:home"))
        self.assertFalse(storefront.wsgi_request.user.is_authenticated)

    def test_member_and_admin_sessions_can_coexist(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": self.admin.email,
                "password": "Admin-session1!",
                "next": reverse("admin:index"),
            },
        )

        self.assertRedirects(response, reverse("admin:index"))
        storefront = self.client.get(reverse("core:home"))
        self.assertEqual(storefront.wsgi_request.user.pk, self.member.pk)
        admin_page = self.client.get(reverse("admin:index"))
        self.assertEqual(admin_page.wsgi_request.user.pk, self.admin.pk)
