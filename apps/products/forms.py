from django import forms

from .models import Product
from .validators import validate_routine_file, validate_thumbnail


class ProductForm(forms.ModelForm):
    thumbnail_file = forms.FileField(
        label="상품 썸네일",
        required=False,
        validators=[validate_thumbnail],
        help_text="JPG, PNG 또는 WEBP, 최대 5MB",
    )
    routine_file = forms.FileField(
        label="운동 루틴 파일",
        required=False,
        validators=[validate_routine_file],
        help_text="XLSX 형식, 최대 20MB",
    )

    class Meta:
        model = Product
        fields = (
            "title",
            "short_description",
            "description",
            "category",
            "goals",
            "difficulty",
            "duration_weeks",
            "sessions_per_week",
            "price",
            "status",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "goals": forms.CheckboxSelectMultiple(),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk:
            if not cleaned_data.get("thumbnail_file"):
                self.add_error("thumbnail_file", "새 상품에는 썸네일이 필요합니다.")
            if not cleaned_data.get("routine_file"):
                self.add_error("routine_file", "새 상품에는 운동 루틴 파일이 필요합니다.")
        return cleaned_data
