from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "author", "rating", "is_visible", "created_at")
    list_filter = ("rating", "is_visible", "created_at")
    search_fields = ("product__title", "author__email", "author__nickname", "content")
    readonly_fields = ("author", "product", "order_item", "rating", "content", "created_at", "updated_at")
    list_editable = ("is_visible",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
