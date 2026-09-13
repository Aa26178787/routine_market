import logging

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


audit_logger = logging.getLogger("accounts.audit")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "email",
        "nickname",
        "full_name",
        "role",
        "is_active",
        "is_staff",
        "created_at",
    )
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "nickname", "full_name")
    readonly_fields = ("last_login", "date_joined", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("프로필", {"fields": ("full_name", "nickname", "role")}),
        (
            "권한",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("기록", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "full_name",
                    "nickname",
                    "role",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        security_fields = {
            "email",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        }
        changed_security_fields = sorted(security_fields.intersection(form.changed_data))
        if changed_security_fields:
            audit_logger.warning(
                "admin_user_security_change actor_user_id=%s target_user_id=%s fields=%s",
                request.user.pk,
                obj.pk,
                ",".join(changed_security_fields),
            )

    def delete_model(self, request, obj):
        audit_logger.warning(
            "admin_user_delete actor_user_id=%s target_user_id=%s",
            request.user.pk,
            obj.pk,
        )
        super().delete_model(request, obj)
