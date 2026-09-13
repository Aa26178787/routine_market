import re
import time

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.trainers.models import TrainerProfile


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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SignUpViewTests(TestCase):
    def mark_email_verified(self, email):
        session = self.client.session
        session["signup_verified_email"] = {
            "email": email.lower(),
            "verified_at": time.time(),
        }
        session.save()

    def test_trainer_application_redirect_explains_login_requirement(self):
        response = self.client.get(reverse("trainers:application_form"), follow=True)

        self.assertRedirects(
            response,
            f'{reverse("accounts:login")}?next={reverse("trainers:application_form")}',
        )
        self.assertContains(response, "트레이너 신청을 위해 로그인해 주세요")
        self.assertContains(response, "로그인하고 트레이너 신청하기")

    def test_general_signup_tab_leaves_trainer_flow(self):
        response = self.client.get(
            reverse("accounts:signup"),
            {"next": reverse("trainers:application_form")},
        )

        self.assertContains(
            response,
            f'href="{reverse("accounts:signup")}"',
            html=False,
        )
        self.assertNotContains(
            response,
            f'href="{reverse("accounts:signup")}?next=%2Ftrainers%2Fapply%2F"',
            html=False,
        )

    def test_trainer_tab_and_start_card_share_signup_destination(self):
        response = self.client.get(reverse("accounts:login"))
        destination = (
            f'{reverse("accounts:signup")}?next={reverse("trainers:application_form")}'
        )

        self.assertContains(response, f'href="{destination}"', count=2, html=False)

    def test_trainer_signup_continues_to_application(self):
        self.mark_email_verified("trainer-start@example.com")
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "trainer-start@example.com",
                "full_name": "트레이너 신청자",
                "nickname": "trainer-start",
                "password1": "safe-test-password-2026",
                "password2": "safe-test-password-2026",
                "next": reverse("trainers:application_form"),
            },
        )

        self.assertRedirects(response, reverse("trainers:application_form"))

    def test_signup_rejects_external_next_url(self):
        self.mark_email_verified("safe-next@example.com")
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "safe-next@example.com",
                "full_name": "안전한 사용자",
                "nickname": "safe-next",
                "password1": "safe-test-password-2026",
                "password2": "safe-test-password-2026",
                "next": "https://example.org/steal-session",
            },
        )

        self.assertRedirects(response, reverse("core:home"))

    def test_signup_creates_and_logs_in_member(self):
        self.mark_email_verified("new@example.com")
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
        self.assertIsNotNone(user.email_verified_at)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_requires_verified_email(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "unverified@example.com",
                "full_name": "미인증 회원",
                "nickname": "unverified-member",
                "password1": "safe-test-password-2026",
                "password2": "safe-test-password-2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "이메일 인증을 완료해 주세요")
        self.assertFalse(get_user_model().objects.filter(email="unverified@example.com").exists())

    def test_email_and_nickname_availability_is_case_insensitive(self):
        get_user_model().objects.create_user(
            email="used@example.com",
            nickname="UsedNickname",
            full_name="기존 회원",
            password="safe-test-password-2026",
        )

        email_response = self.client.get(
            reverse("accounts:signup_availability"),
            {"field": "email", "value": "USED@example.com"},
        )
        nickname_response = self.client.get(
            reverse("accounts:signup_availability"),
            {"field": "nickname", "value": "usednickname"},
        )

        self.assertFalse(email_response.json()["available"])
        self.assertFalse(nickname_response.json()["available"])

    def test_email_code_can_be_sent_and_confirmed(self):
        email = "verify@example.com"
        send_response = self.client.post(
            reverse("accounts:send_signup_email_code"), {"email": email}
        )

        self.assertEqual(send_response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"(\d{6})", mail.outbox[0].body).group(1)
        confirm_response = self.client.post(
            reverse("accounts:confirm_signup_email_code"),
            {"email": email, "code": code},
        )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertTrue(confirm_response.json()["ok"])
        self.assertEqual(self.client.session["signup_verified_email"]["email"], email)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountManagementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="profile@example.com",
            password="safe-test-password-2026",
            full_name="기존 이름",
            nickname="old-nickname",
        )

    def test_member_can_update_profile_without_changing_email_or_role(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:profile_update"),
            {
                "email": "Updated@Example.com",
                "full_name": "수정 이름",
                "nickname": "new-nickname",
            },
        )

        self.assertRedirects(response, reverse("accounts:profile_update"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile@example.com")
        self.assertEqual(self.user.nickname, "new-nickname")
        self.assertEqual(self.user.role, get_user_model().Role.MEMBER)

    def test_email_changes_only_after_new_address_is_verified(self):
        self.client.force_login(self.user)

        send_response = self.client.post(
            reverse("accounts:email_change"),
            {"action": "send", "email": "NewAddress@Example.com"},
        )

        self.assertRedirects(send_response, reverse("accounts:email_change"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile@example.com")
        code = re.search(r"(\d{6})", mail.outbox[-1].body).group(1)

        with self.assertLogs("accounts.audit", level="WARNING"):
            confirm_response = self.client.post(
                reverse("accounts:email_change"),
                {"action": "confirm", "code": code},
            )

        self.assertRedirects(confirm_response, reverse("accounts:profile_update"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "newaddress@example.com")
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_email_change_code_does_not_change_email(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("accounts:email_change"),
            {"action": "send", "email": "new@example.com"},
        )

        response = self.client.post(
            reverse("accounts:email_change"),
            {"action": "confirm", "code": "000000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "인증번호가 일치하지 않습니다")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile@example.com")

    def test_password_change_keeps_user_logged_in(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "safe-test-password-2026",
                "new_password1": "new-safe-test-password-2026",
                "new_password2": "new-safe-test-password-2026",
            },
        )

        self.assertRedirects(response, reverse("accounts:password_change_done"))
        self.assertIn("_auth_user_id", self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-safe-test-password-2026"))

    def test_password_reset_sends_link_for_known_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.user.email},
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/password/reset/", mail.outbox[0].body)

    def test_deactivation_get_only_shows_confirmation(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:account_deactivate"))

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_deactivation_requires_current_password_and_confirmation(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:account_deactivate"),
            {"password": "wrong-password", "confirm": "on"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "현재 비밀번호가 올바르지 않습니다")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_user_can_deactivate_only_own_account_and_is_logged_out(self):
        other = get_user_model().objects.create_user(
            email="other@example.com",
            password="safe-test-password-2026",
            full_name="다른 회원",
            nickname="other-member",
        )
        self.client.force_login(self.user)

        with self.assertLogs("accounts.audit", level="WARNING") as logs:
            response = self.client.post(
                reverse("accounts:account_deactivate"),
                {"password": "safe-test-password-2026", "confirm": "on"},
            )

        self.assertRedirects(response, reverse("core:home"))
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(other.is_active)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn(f"target_user_id={self.user.pk}", logs.output[0])


class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="login@example.com",
            password="safe-test-password-2026",
            full_name="로그인 회원",
            nickname="login-member",
        )

    def tearDown(self):
        cache.clear()

    def test_repeated_failed_login_is_temporarily_blocked(self):
        for _ in range(4):
            response = self.client.post(
                reverse("accounts:login"),
                {"username": self.user.email, "password": "wrong-password"},
            )
            self.assertNotContains(response, "로그인 시도가 너무 많습니다")

        blocked = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": "wrong-password"},
        )
        valid_while_blocked = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": "safe-test-password-2026"},
        )

        self.assertContains(blocked, "로그인 시도가 너무 많습니다")
        self.assertContains(valid_while_blocked, "로그인 시도가 너무 많습니다")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_clears_previous_failures(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": "wrong-password"},
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": "safe-test-password-2026"},
        )

        self.assertRedirects(response, reverse("core:home"))
        self.client.logout()
        for _ in range(4):
            response = self.client.post(
                reverse("accounts:login"),
                {"username": self.user.email, "password": "wrong-password"},
            )
        self.assertNotContains(response, "로그인 시도가 너무 많습니다")


class RoleDirectAccessTests(TestCase):
    def setUp(self):
        self.member = get_user_model().objects.create_user(
            email="member-access@example.com",
            password="safe-test-password-2026",
            full_name="일반 회원",
            nickname="member-access",
        )
        self.trainer_user = get_user_model().objects.create_user(
            email="trainer-access@example.com",
            password="safe-test-password-2026",
            full_name="트레이너",
            nickname="trainer-access",
            role=get_user_model().Role.TRAINER,
        )
        self.trainer = TrainerProfile.objects.create(
            user=self.trainer_user,
            specialty="근력 운동",
            career_years=3,
            introduction="소개",
            is_verified=True,
            verified_at=timezone.now(),
        )

    def test_anonymous_user_is_redirected_from_account_and_role_pages(self):
        for url in (
            reverse("accounts:profile_update"),
            reverse("accounts:account_deactivate"),
            reverse("trainers:profile_update"),
            reverse("products:seller_dashboard"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_member_cannot_open_trainer_only_pages_by_url(self):
        self.client.force_login(self.member)

        for url in (
            reverse("trainers:profile_update"),
            reverse("products:seller_dashboard"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_verified_trainer_can_open_own_trainer_pages(self):
        self.client.force_login(self.trainer_user)

        self.assertEqual(self.client.get(reverse("trainers:profile_update")).status_code, 200)
        self.assertEqual(self.client.get(reverse("products:seller_dashboard")).status_code, 200)
