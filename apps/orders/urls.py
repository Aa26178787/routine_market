from django.urls import path

from . import views


app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("items/<int:order_item_id>/download/", views.download_order_item, name="download"),
    path("<uuid:order_number>/", views.order_detail, name="detail"),
    path("<uuid:order_number>/pay/", views.pay_order, name="pay"),
    path("<uuid:order_number>/cancel/", views.cancel_order, name="cancel"),
    path("purchases/history/", views.purchase_history, name="purchase_history"),
]
