from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class TrainerApplication(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "심사 대기"
        APPROVED = "APPROVED", "승인"
        REJECTED = "REJECTED", "거절"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trainer_application",
        verbose_name="신청자",
    )
    specialty = models.CharField("전문 운동 분야", max_length=100)
    career_years = models.PositiveSmallIntegerField("경력 연수")
    career_description = models.TextField("경력 상세")
    introduction = models.TextField("자기소개")
    activity_url = models.URLField("활동 URL", blank=True)
    status = models.CharField(
        "상태", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    rejection_reason = models.TextField("거절 사유", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_trainer_applications",
        verbose_name="심사자",
    )
    submitted_at = models.DateTimeField("제출시각")
    reviewed_at = models.DateTimeField("심사시각", null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "트레이너 인증 신청"
        verbose_name_plural = "트레이너 인증 신청"
        indexes = [models.Index(fields=["status", "submitted_at"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~Q(status="APPROVED")
                    | (Q(reviewed_by__isnull=False) & Q(reviewed_at__isnull=False))
                ),
                name="trainer_approved_has_reviewer",
            ),
            models.CheckConstraint(
                condition=~Q(status="REJECTED") | ~Q(rejection_reason=""),
                name="trainer_rejected_has_reason",
            ),
        ]

    def clean(self):
        errors = {}
        if self.status == self.Status.APPROVED and (
            not self.reviewed_by_id or not self.reviewed_at
        ):
            errors["status"] = "승인 상태에는 심사자와 심사시각이 필요합니다."
        if self.status == self.Status.REJECTED and not self.rejection_reason.strip():
            errors["rejection_reason"] = "거절 사유를 입력해야 합니다."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.user.nickname} - {self.get_status_display()}"


class Certification(models.Model):
    application = models.ForeignKey(
        TrainerApplication,
        on_delete=models.CASCADE,
        related_name="certifications",
        verbose_name="인증 신청",
    )
    name = models.CharField("자격증명", max_length=150)
    issuer = models.CharField("발급기관", max_length=150)
    country_code = models.CharField("국가 코드", max_length=2, default="KR")
    credential_number = models.CharField("자격번호", max_length=100, blank=True)
    evidence_object_key = models.CharField("증빙 객체 키", max_length=500)
    original_filename = models.CharField("원본 파일명", max_length=255)
    uploaded_at = models.DateTimeField("업로드시각", auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "트레이너 자격"
        verbose_name_plural = "트레이너 자격"

    def __str__(self):
        return f"{self.name} ({self.issuer})"


class TrainerProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="trainer_profile",
        verbose_name="회원",
    )
    specialty = models.CharField("대표 전문 분야", max_length=100)
    career_years = models.PositiveSmallIntegerField("경력 연수")
    introduction = models.TextField("공개 자기소개")
    activity_url = models.URLField("활동 URL", blank=True)
    is_verified = models.BooleanField("인증 여부", default=True)
    verified_at = models.DateTimeField("승인시각")

    class Meta:
        ordering = ["user__nickname"]
        verbose_name = "트레이너 프로필"
        verbose_name_plural = "트레이너 프로필"

    def __str__(self):
        return self.user.nickname
