from django.urls import path

from . import views


app_name = "reviews"

urlpatterns = [
    path("order-items/<int:order_item_id>/new/", views.review_create, name="create"),
    path("<int:pk>/edit/", views.review_update, name="update"),
    path("<int:pk>/delete/", views.review_delete, name="delete"),
]
