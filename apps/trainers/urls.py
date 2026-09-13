from django.urls import path

from . import views


app_name = "trainers"

urlpatterns = [
    path("apply/", views.application_form, name="application_form"),
    path("application/", views.application_status, name="application_status"),
    path("profile/edit/", views.trainer_profile_update, name="profile_update"),
    path("<int:pk>/", views.trainer_detail, name="detail"),
]
