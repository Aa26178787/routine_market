from django.contrib import admin

from .models import Category, ExerciseGoal, Product, ProductFile, ProductGoal, WishlistItem


class ProductFileInline(admin.TabularInline):
    model = ProductFile
    extra = 0
    readonly_fields = ("created_at",)


class ProductGoalInline(admin.TabularInline):
    model = ProductGoal
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "seller",
        "category",
        "difficulty",
        "price",
        "status",
        "created_at",
    )
    list_filter = ("status", "category", "difficulty")
    search_fields = ("title", "short_description", "description", "seller__user__nickname")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at", "published_at")
    inlines = [ProductGoalInline, ProductFileInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ExerciseGoal)
class ExerciseGoalAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ProductFile)
class ProductFileAdmin(admin.ModelAdmin):
    list_display = ("product", "version", "original_filename", "size_bytes", "is_current")
    list_filter = ("is_current", "content_type")
    search_fields = ("product__title", "original_filename", "object_key")


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__email", "product__title")
