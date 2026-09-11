import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Certification, TrainerApplication, TrainerProfile
from .services import approve_trainer, reject_trainer


class TrainerApprovalTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.member = user_model.objects.create_user(
            email="trainer@example.com",
            password="safe-test-password",
            full_name="트레이너",
            nickname="trainer",
        )
        self.admin = user_model.objects.create_superuser(
            email="admin@example.com",
            password="safe-test-password",
            full_name="관리자",
            nickname="admin",
        )
        self.application = TrainerApplication.objects.create(
            user=self.member,
            specialty="보디빌딩",
            career_years=3,
            career_description="3년 지도 경력",
            introduction="안전한 운동을 지도합니다.",
            submitted_at=timezone.now(),
        )

    def test_approval_creates_profile_and_changes_role(self):
        profile = approve_trainer(application_id=self.application.pk, reviewer=self.admin)

        self.application.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(self.application.status, TrainerApplication.Status.APPROVED)
        self.assertEqual(self.member.role, get_user_model().Role.TRAINER)
        self.assertEqual(profile.user, self.member)
        self.assertTrue(TrainerProfile.objects.filter(user=self.member).exists())

    def test_rejection_records_reason_reviewer_and_time(self):
        rejected = reject_trainer(
            application_id=self.application.pk,
            reviewer=self.admin,
            reason="증빙 자료의 자격번호를 확인할 수 없습니다.",
        )

        self.assertEqual(rejected.status, TrainerApplication.Status.REJECTED)
        self.assertEqual(rejected.reviewed_by, self.admin)
        self.assertIsNotNone(rejected.reviewed_at)
        self.assertEqual(
            rejected.rejection_reason,
            "증빙 자료의 자격번호를 확인할 수 없습니다.",
        )

    def test_admin_reject_action_requires_reason_and_rejects_application(self):
        self.client.force_login(self.admin)
        changelist_url = reverse("admin:trainers_trainerapplication_changelist")
        selection = {
            "action": "reject_selected",
            "_selected_action": str(self.application.pk),
        }

        confirmation = self.client.post(changelist_url, selection)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "거절 사유")

        missing_reason = self.client.post(
            changelist_url,
            {**selection, "apply": "yes", "rejection_reason": ""},
        )
        self.assertEqual(missing_reason.status_code, 200)
        self.assertContains(missing_reason, "거절 사유를 입력해야 합니다")

        response = self.client.post(
            changelist_url,
            {
                **selection,
                "apply": "yes",
                "rejection_reason": "제출된 증빙을 확인할 수 없습니다.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, TrainerApplication.Status.REJECTED)
        self.assertEqual(self.application.reviewed_by, self.admin)
        self.assertEqual(
            self.application.rejection_reason,
            "제출된 증빙을 확인할 수 없습니다.",
        )


class TrainerApplicationViewTests(TestCase):
    def setUp(self):
        self.member = get_user_model().objects.create_user(
            email="applicant@example.com",
            password="safe-test-password",
            full_name="신청자",
            nickname="applicant",
        )
        self.client.force_login(self.member)

    def test_member_can_submit_application_with_pdf_evidence(self):
        evidence = SimpleUploadedFile(
            "certificate.pdf",
            b"%PDF-1.4\n% test certificate",
            content_type="application/pdf",
        )
        payload = {
            "specialty": "파워리프팅",
            "career_years": 3,
            "career_description": "3년 지도 경력",
            "introduction": "안전하게 지도합니다.",
            "activity_url": "https://example.com/trainer",
            "certifications-TOTAL_FORMS": "1",
            "certifications-INITIAL_FORMS": "0",
            "certifications-MIN_NUM_FORMS": "1",
            "certifications-MAX_NUM_FORMS": "1000",
            "certifications-0-name": "생활스포츠지도사 2급",
            "certifications-0-issuer": "국민체육진흥공단",
            "certifications-0-country_code": "KR",
            "certifications-0-credential_number": "TEST-001",
            "certifications-0-evidence_file": evidence,
        }

        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("trainers:application_form"), payload)

        self.assertRedirects(response, reverse("trainers:application_status"))
        application = TrainerApplication.objects.get(user=self.member)
        certification = Certification.objects.get(application=application)
        self.assertEqual(application.status, TrainerApplication.Status.PENDING)
        self.assertTrue(certification.evidence_object_key.endswith(".pdf"))

    def test_pending_application_redirects_to_status(self):
        TrainerApplication.objects.create(
            user=self.member,
            specialty="러닝",
            career_years=2,
            career_description="경력",
            introduction="소개",
            submitted_at=timezone.now(),
        )

        response = self.client.get(reverse("trainers:application_form"))

        self.assertRedirects(response, reverse("trainers:application_status"))
