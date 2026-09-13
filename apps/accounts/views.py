import secrets
import time
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    AccountDeactivationForm,
    EmailChangeConfirmForm,
    EmailChangeRequestForm,
    ProfileForm,
    SignUpForm,
)
from .models import User


logger = logging.getLogger(__name__)
EMAIL_CODE_TTL_SECONDS = 300
EMAIL_VERIFIED_TTL_SECONDS = 1800
EMAIL_RESEND_SECONDS = 60
EMAIL_MAX_ATTEMPTS = 5
EMAIL_CHANGE_SESSION_KEY = "account_email_change"


def _normalized_email(value):
    return (value or "").strip().lower()


def _email_code_digest(email, code):
    return salted_hmac("accounts.signup-email", f"{email}:{code}").hexdigest()


def _verified_email(request):
    verified = request.session.get("signup_verified_email") or {}
    if time.time() - verified.get("verified_at", 0) > EMAIL_VERIFIED_TTL_SECONDS:
        request.session.pop("signup_verified_email", None)
        return ""
    return _normalized_email(verified.get("email"))


def signup_availability(request):
    if request.method != "GET":
        return JsonResponse({"available": False, "message": "잘못된 요청입니다."}, status=405)

    field = request.GET.get("field", "")
    value = (request.GET.get("value") or "").strip()
    if field == "email":
        value = _normalized_email(value)
        try:
            validate_email(value)
        except ValidationError:
            return JsonResponse({"available": False, "message": "올바른 이메일 주소를 입력해 주세요."})
        exists = User.objects.filter(email__iexact=value).exists()
        message = "사용 가능한 이메일입니다." if not exists else "이미 사용 중인 이메일입니다."
    elif field == "nickname":
        if not value or len(value) > 50:
            return JsonResponse({"available": False, "message": "닉네임은 1~50자로 입력해 주세요."})
        exists = User.objects.filter(nickname__iexact=value).exists()
        message = "사용 가능한 닉네임입니다." if not exists else "이미 사용 중인 닉네임입니다."
    else:
        return JsonResponse({"available": False, "message": "확인할 항목이 올바르지 않습니다."}, status=400)

    return JsonResponse({"available": not exists, "message": message})


def send_signup_email_code(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "잘못된 요청입니다."}, status=405)

    email = _normalized_email(request.POST.get("email"))
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"ok": False, "message": "올바른 이메일 주소를 입력해 주세요."}, status=400)
    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({"ok": False, "message": "이미 사용 중인 이메일입니다."}, status=400)

    now = time.time()
    previous = request.session.get("signup_email_verification") or {}
    remaining = EMAIL_RESEND_SECONDS - int(now - previous.get("sent_at", 0))
    if previous.get("email") == email and remaining > 0:
        return JsonResponse(
            {"ok": False, "message": f"{remaining}초 후에 인증번호를 다시 받을 수 있습니다."},
            status=429,
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    request.session["signup_email_verification"] = {
        "email": email,
        "digest": _email_code_digest(email, code),
        "expires_at": now + EMAIL_CODE_TTL_SECONDS,
        "sent_at": now,
        "attempts": 0,
    }
    request.session.pop("signup_verified_email", None)
    try:
        send_mail(
            "[루틴마켓] 회원가입 이메일 인증번호",
            f"루틴마켓 회원가입 인증번호는 {code}입니다. 인증번호는 5분 동안 유효합니다.",
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
    except Exception:
        request.session.pop("signup_email_verification", None)
        logger.exception("회원가입 인증 메일 발송 실패")
        return JsonResponse(
            {"ok": False, "message": "인증 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요."},
            status=503,
        )
    return JsonResponse(
        {
            "ok": True,
            "message": "인증번호를 발송했습니다. 메일함을 확인해 주세요.",
            "expires_in": EMAIL_CODE_TTL_SECONDS,
            "resend_after": EMAIL_RESEND_SECONDS,
        }
    )


def confirm_signup_email_code(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "잘못된 요청입니다."}, status=405)

    email = _normalized_email(request.POST.get("email"))
    code = (request.POST.get("code") or "").strip()
    state = request.session.get("signup_email_verification") or {}
    if state.get("email") != email:
        return JsonResponse({"ok": False, "message": "먼저 현재 이메일로 인증번호를 받아 주세요."}, status=400)
    if time.time() > state.get("expires_at", 0):
        request.session.pop("signup_email_verification", None)
        return JsonResponse({"ok": False, "message": "인증번호가 만료되었습니다. 다시 발송해 주세요."}, status=400)
    if state.get("attempts", 0) >= EMAIL_MAX_ATTEMPTS:
        request.session.pop("signup_email_verification", None)
        return JsonResponse({"ok": False, "message": "인증 시도 횟수를 초과했습니다. 다시 발송해 주세요."}, status=429)

    if not constant_time_compare(state.get("digest", ""), _email_code_digest(email, code)):
        state["attempts"] = state.get("attempts", 0) + 1
        request.session["signup_email_verification"] = state
        return JsonResponse({"ok": False, "message": "인증번호가 일치하지 않습니다."}, status=400)

    request.session["signup_verified_email"] = {"email": email, "verified_at": time.time()}
    request.session.pop("signup_email_verification", None)
    return JsonResponse({"ok": True, "message": "이메일 인증이 완료되었습니다."})


def signup(request):
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = ""
    if request.user.is_authenticated:
        return redirect(next_url or "core:home")

    verified_email = _verified_email(request)
    if request.method == "POST":
        if _normalized_email(request.POST.get("email")) != verified_email:
            request.session.pop("signup_verified_email", None)
            verified_email = ""
        form = SignUpForm(request.POST, verified_email=verified_email)
        if form.is_valid():
            user = form.save()
            request.session.pop("signup_verified_email", None)
            login(request, user)
            messages.success(request, "회원가입이 완료되었습니다.")
            return redirect(next_url or "core:home")
    else:
        form = SignUpForm(
            initial={"email": verified_email} if verified_email else None,
            verified_email=verified_email,
        )

    return render(
        request,
        "accounts/signup.html",
        {"form": form, "next": next_url, "verified_email": verified_email},
    )


@login_required
def profile_update(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "회원 정보가 수정되었습니다.")
            return redirect("accounts:profile_update")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile_form.html", {"form": form})


@login_required
def email_change(request):
    request_form = EmailChangeRequestForm(request.user)
    confirm_form = EmailChangeConfirmForm()
    pending = request.session.get(EMAIL_CHANGE_SESSION_KEY) or {}

    if request.method == "POST" and request.POST.get("action") == "send":
        request_form = EmailChangeRequestForm(request.user, request.POST)
        if request_form.is_valid():
            email = request_form.cleaned_data["email"]
            now = time.time()
            remaining = EMAIL_RESEND_SECONDS - int(now - pending.get("sent_at", 0))
            if pending.get("email") == email and remaining > 0:
                request_form.add_error(
                    "email", f"{remaining}초 후에 인증번호를 다시 받을 수 있습니다."
                )
            else:
                code = f"{secrets.randbelow(1_000_000):06d}"
                request.session[EMAIL_CHANGE_SESSION_KEY] = {
                    "user_id": request.user.pk,
                    "email": email,
                    "digest": _email_code_digest(email, code),
                    "expires_at": now + EMAIL_CODE_TTL_SECONDS,
                    "sent_at": now,
                    "attempts": 0,
                }
                try:
                    send_mail(
                        "[루틴마켓] 이메일 변경 인증번호",
                        f"루틴마켓 이메일 변경 인증번호는 {code}입니다. 인증번호는 5분 동안 유효합니다.",
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                    )
                except Exception:
                    request.session.pop(EMAIL_CHANGE_SESSION_KEY, None)
                    logger.exception("이메일 변경 인증 메일 발송 실패")
                    request_form.add_error(
                        None, "인증 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요."
                    )
                else:
                    messages.success(request, "새 이메일로 인증번호를 보냈습니다.")
                    return redirect("accounts:email_change")

    elif request.method == "POST" and request.POST.get("action") == "confirm":
        confirm_form = EmailChangeConfirmForm(request.POST)
        pending = request.session.get(EMAIL_CHANGE_SESSION_KEY) or {}
        if confirm_form.is_valid():
            if pending.get("user_id") != request.user.pk:
                confirm_form.add_error(None, "먼저 새 이메일로 인증번호를 받아 주세요.")
            elif time.time() > pending.get("expires_at", 0):
                request.session.pop(EMAIL_CHANGE_SESSION_KEY, None)
                confirm_form.add_error(None, "인증번호가 만료되었습니다. 다시 발송해 주세요.")
            elif pending.get("attempts", 0) >= EMAIL_MAX_ATTEMPTS:
                request.session.pop(EMAIL_CHANGE_SESSION_KEY, None)
                confirm_form.add_error(None, "인증 시도 횟수를 초과했습니다. 다시 발송해 주세요.")
            elif not constant_time_compare(
                pending.get("digest", ""),
                _email_code_digest(pending.get("email", ""), confirm_form.cleaned_data["code"]),
            ):
                pending["attempts"] = pending.get("attempts", 0) + 1
                request.session[EMAIL_CHANGE_SESSION_KEY] = pending
                confirm_form.add_error("code", "인증번호가 일치하지 않습니다.")
            elif User.objects.exclude(pk=request.user.pk).filter(
                email__iexact=pending["email"]
            ).exists():
                request.session.pop(EMAIL_CHANGE_SESSION_KEY, None)
                confirm_form.add_error(None, "이미 사용 중인 이메일입니다.")
            else:
                request.user.email = pending["email"]
                request.user.email_verified_at = timezone.now()
                request.user.save(update_fields=["email", "email_verified_at", "updated_at"])
                request.session.pop(EMAIL_CHANGE_SESSION_KEY, None)
                logging.getLogger("accounts.audit").warning(
                    "account_email_changed actor_user_id=%s target_user_id=%s",
                    request.user.pk,
                    request.user.pk,
                )
                messages.success(request, "이메일이 변경되고 인증되었습니다.")
                return redirect("accounts:profile_update")

    pending = request.session.get(EMAIL_CHANGE_SESSION_KEY) or {}
    return render(
        request,
        "accounts/email_change.html",
        {
            "request_form": request_form,
            "confirm_form": confirm_form,
            "pending_email": pending.get("email", ""),
        },
    )


@login_required
def password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "비밀번호가 변경되었습니다.")
            return redirect("accounts:password_change_done")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "accounts/password_change_form.html", {"form": form})


@login_required
def password_change_done(request):
    return render(request, "accounts/password_change_done.html")


@login_required
def account_deactivate(request):
    if request.method == "POST":
        form = AccountDeactivationForm(request.user, request.POST)
        if form.is_valid():
            user = request.user
            user_id = user.pk
            user.is_active = False
            user.save(update_fields=["is_active", "updated_at"])
            logging.getLogger("accounts.audit").warning(
                "account_deactivated actor_user_id=%s target_user_id=%s",
                user_id,
                user_id,
            )
            logout(request)
            messages.success(request, "계정이 안전하게 비활성화되었습니다.")
            return redirect("core:home")
    else:
        form = AccountDeactivationForm(request.user)
    return render(request, "accounts/account_deactivate.html", {"form": form})
