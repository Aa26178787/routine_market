from django.contrib import admin

from .models import Cart, CartItem, DownloadLog, Order, OrderItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    search_fields = ("user__email", "user__nickname")
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "product_file",
        "seller",
        "product_title",
        "seller_name",
        "unit_price",
        "created_at",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "buyer",
        "status",
        "total_amount",
        "payment_provider",
        "payment_method",
        "paid_at",
        "created_at",
    )
    list_filter = ("status", "payment_provider", "payment_method", "created_at", "paid_at")
    search_fields = ("order_number", "payment_key", "buyer__email", "buyer__nickname")
    readonly_fields = (
        "order_number",
        "buyer",
        "status",
        "total_amount",
        "paid_at",
        "cancelled_at",
        "payment_provider",
        "payment_key",
        "payment_method",
        "payment_receipt_url",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DownloadLog)
class DownloadLogAdmin(admin.ModelAdmin):
    list_display = ("user", "order_item", "ip_address", "created_at")
    search_fields = ("user__email", "order_item__product_title")
    readonly_fields = ("user", "order_item", "ip_address", "user_agent", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
