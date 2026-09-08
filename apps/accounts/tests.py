from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class UserModelTests(TestCase):
    def test_create_user_uses_email_for_login(self):
        user = get_user_model().objects.create_user(
            email="Member@Example.com",
            password="safe-test-password",
            full_name="테스트 회원",
            nickname="member",
        )

        self.assertEqual(user.email, "Member@example.com")
        self.assertTrue(user.check_password("safe-test-password"))
        self.assertEqual(user.role, get_user_model().Role.MEMBER)

    def test_create_superuser_sets_admin_flags(self):
        user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="safe-test-password",
            full_name="관리자",
            nickname="admin",
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)


class SignUpViewTests(TestCase):
    def test_signup_creates_and_logs_in_member(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "new@example.com",
                "full_name": "신규 회원",
                "nickname": "new-member",
                "password1": "safe-test-password-2026",
                "password2": "safe-test-password-2026",
            },
        )

        self.assertRedirects(response, reverse("core:home"))
        user = get_user_model().objects.get(email="new@example.com")
        self.assertEqual(user.role, get_user_model().Role.MEMBER)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
