from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import TrainerApplication, TrainerProfile


@transaction.atomic
def approve_trainer(*, application_id: int, reviewer: User) -> TrainerProfile:
    if not reviewer.is_staff:
        raise PermissionDenied("관리자만 트레이너 신청을 승인할 수 있습니다.")

    application = TrainerApplication.objects.select_for_update().select_related("user").get(
        pk=application_id
    )
    if application.status != TrainerApplication.Status.PENDING:
        raise ValidationError("심사 대기 중인 신청만 승인할 수 있습니다.")

    reviewed_at = timezone.now()
    application.status = TrainerApplication.Status.APPROVED
    application.reviewed_by = reviewer
    application.reviewed_at = reviewed_at
    application.rejection_reason = ""
    application.full_clean()
    application.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "updated_at",
        ]
    )

    profile, _ = TrainerProfile.objects.update_or_create(
        user=application.user,
        defaults={
            "specialty": application.specialty,
            "career_years": application.career_years,
            "introduction": application.introduction,
            "activity_url": application.activity_url,
            "is_verified": True,
            "verified_at": reviewed_at,
        },
    )
    application.user.role = User.Role.TRAINER
    application.user.save(update_fields=["role", "updated_at"])
    return profile


@transaction.atomic
def reject_trainer(*, application_id: int, reviewer: User, reason: str) -> TrainerApplication:
    if not reviewer.is_staff:
        raise PermissionDenied("관리자만 트레이너 신청을 거절할 수 있습니다.")
    if not reason.strip():
        raise ValidationError("거절 사유를 입력해야 합니다.")

    application = TrainerApplication.objects.select_for_update().get(pk=application_id)
    if application.status != TrainerApplication.Status.PENDING:
        raise ValidationError("심사 대기 중인 신청만 거절할 수 있습니다.")

    application.status = TrainerApplication.Status.REJECTED
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.rejection_reason = reason.strip()
    application.full_clean()
    application.save()
    return application
