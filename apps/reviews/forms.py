from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        label="평점",
        choices=[(value, f"{value}점") for value in range(5, 0, -1)],
        coerce=int,
        widget=forms.RadioSelect(),
    )

    class Meta:
        model = Review
        fields = ("rating", "content")
        widgets = {
            "content": forms.Textarea(
                attrs={"rows": 6, "placeholder": "프로그램을 이용한 경험을 작성해주세요."}
            )
        }

    def clean_content(self):
        content = self.cleaned_data["content"].strip()
        if len(content) < 10:
            raise forms.ValidationError("리뷰는 10자 이상 작성해주세요.")
        return content
