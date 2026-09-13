from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import RateLimitedAuthenticationForm


app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("signup/availability/", views.signup_availability, name="signup_availability"),
    path("signup/email/send/", views.send_signup_email_code, name="send_signup_email_code"),
    path("signup/email/confirm/", views.confirm_signup_email_code, name="confirm_signup_email_code"),
    path("profile/", views.profile_update, name="profile_update"),
    path("email/change/", views.email_change, name="email_change"),
    path("password/change/", views.password_change, name="password_change"),
    path("deactivate/", views.account_deactivate, name="account_deactivate"),
    path(
        "password/change/done/",
        views.password_change_done,
        name="password_change_done",
    ),
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=RateLimitedAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
