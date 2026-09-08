from django.contrib import admin, messages

from .models import Certification, TrainerApplication, TrainerProfile
from .services import approve_trainer


class CertificationInline(admin.TabularInline):
    model = Certification
    extra = 0


@admin.register(TrainerApplication)
class TrainerApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "specialty", "career_years", "status", "submitted_at")
    list_filter = ("status", "specialty")
    search_fields = ("user__email", "user__nickname", "specialty")
    readonly_fields = ("reviewed_by", "reviewed_at", "created_at", "updated_at")
    inlines = [CertificationInline]
    actions = ["approve_selected"]

    @admin.action(description="선택한 심사 대기 신청 승인")
    def approve_selected(self, request, queryset):
        approved_count = 0
        for application in queryset:
            if application.status == TrainerApplication.Status.PENDING:
                approve_trainer(application_id=application.pk, reviewer=request.user)
                approved_count += 1
        self.message_user(request, f"{approved_count}건을 승인했습니다.", messages.SUCCESS)


@admin.register(TrainerProfile)
class TrainerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "specialty", "career_years", "is_verified", "verified_at")
    list_filter = ("is_verified", "specialty")
    search_fields = ("user__email", "user__nickname", "specialty")


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ("name", "issuer", "country_code", "application", "uploaded_at")
    search_fields = ("name", "issuer", "credential_number", "application__user__email")
