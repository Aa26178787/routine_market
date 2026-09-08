from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name", "nickname")

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_full_name(self):
        return self.cleaned_data["full_name"].strip()

    def clean_nickname(self):
        return self.cleaned_data["nickname"].strip()
