from django.urls import path

from . import views


app_name = "trainers"

urlpatterns = [
    path("apply/", views.application_form, name="application_form"),
    path("application/", views.application_status, name="application_status"),
]
