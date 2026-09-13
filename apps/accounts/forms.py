from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import User
from .security import clear_login_failures, login_block_seconds, record_login_failure


class RateLimitedAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "rate_limited": "로그인 시도가 너무 많습니다. %(seconds)s초 후 다시 시도해 주세요.",
    }

    def clean(self):
        identifier = self.data.get("username", "")
        remaining = login_block_seconds(self.request, identifier)
        if remaining:
            self.is_rate_limited = True
            raise ValidationError(
                self.error_messages["rate_limited"],
                code="rate_limited",
                params={"seconds": remaining},
            )
        try:
            cleaned_data = super().clean()
        except ValidationError:
            if identifier and self.data.get("password"):
                blocked_for = record_login_failure(self.request, identifier)
                if blocked_for:
                    self.is_rate_limited = True
                    raise ValidationError(
                        self.error_messages["rate_limited"],
                        code="rate_limited",
                        params={"seconds": blocked_for},
                    )
            raise
        clear_login_failures(self.request, identifier)
        return cleaned_data


class AccountDeactivationForm(forms.Form):
    password = forms.CharField(
        label="현재 비밀번호",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    confirm = forms.BooleanField(label="계정 비활성화에 동의합니다")

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("현재 비밀번호가 올바르지 않습니다.")
        return password


class SignUpForm(UserCreationForm):
    def __init__(self, *args, verified_email="", **kwargs):
        super().__init__(*args, **kwargs)
        self.verified_email = verified_email.strip().lower()

    class Meta:
        model = User
        fields = ("email", "full_name", "nickname")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("이미 사용 중인 이메일입니다.")
        if email != self.verified_email:
            raise forms.ValidationError("이메일 인증을 완료해 주세요.")
        return email

    def clean_full_name(self):
        return self.cleaned_data["full_name"].strip()

    def clean_nickname(self):
        nickname = self.cleaned_data["nickname"].strip()
        if User.objects.filter(nickname__iexact=nickname).exists():
            raise forms.ValidationError("이미 사용 중인 닉네임입니다.")
        return nickname

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email_verified_at = timezone.now()
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "nickname")

    def clean_full_name(self):
        return self.cleaned_data["full_name"].strip()

    def clean_nickname(self):
        nickname = self.cleaned_data["nickname"].strip()
        if User.objects.exclude(pk=self.instance.pk).filter(
            nickname__iexact=nickname
        ).exists():
            raise forms.ValidationError("이미 사용 중인 닉네임입니다.")
        return nickname



class EmailChangeRequestForm(forms.Form):
    email = forms.EmailField(label="새 이메일")

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email == self.user.email.lower():
            raise forms.ValidationError("현재 이메일과 다른 주소를 입력해 주세요.")
        if User.objects.exclude(pk=self.user.pk).filter(email__iexact=email).exists():
            raise forms.ValidationError("이미 사용 중인 이메일입니다.")
        return email


class EmailChangeConfirmForm(forms.Form):
    code = forms.CharField(label="인증번호", min_length=6, max_length=6)
