from django import forms
from django.forms import inlineformset_factory

from .models import Certification, TrainerApplication
from .validators import validate_certification_file


class TrainerApplicationForm(forms.ModelForm):
    class Meta:
        model = TrainerApplication
        fields = (
            "specialty",
            "career_years",
            "career_description",
            "introduction",
            "activity_url",
        )
        widgets = {
            "career_description": forms.Textarea(attrs={"rows": 4}),
            "introduction": forms.Textarea(attrs={"rows": 5}),
        }
        help_texts = {
            "activity_url": "인스타그램, 블로그 또는 공개 프로필 주소를 입력하세요.",
        }


class CertificationForm(forms.ModelForm):
    evidence_file = forms.FileField(
        label="증빙파일",
        required=False,
        validators=[validate_certification_file],
        help_text="JPG, PNG 또는 PDF, 최대 10MB",
    )

    class Meta:
        model = Certification
        fields = ("name", "issuer", "country_code", "credential_number")

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk and not cleaned_data.get("evidence_file"):
            self.add_error("evidence_file", "새 자격 정보에는 증빙파일이 필요합니다.")
        return cleaned_data


CertificationFormSet = inlineformset_factory(
    TrainerApplication,
    Certification,
    form=CertificationForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
