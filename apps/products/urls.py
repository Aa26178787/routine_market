from django.urls import path

from . import views


app_name = "products"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/<int:product_id>/toggle/", views.wishlist_toggle, name="wishlist_toggle"),
    path("sell/", views.seller_dashboard, name="seller_dashboard"),
    path("sell/new/", views.product_create, name="create"),
    path("sell/<int:pk>/edit/", views.product_update, name="update"),
    path("sell/<int:pk>/suspend/", views.product_suspend, name="suspend"),
    path("<slug:slug>/", views.product_detail, name="detail"),
]
