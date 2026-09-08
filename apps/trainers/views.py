from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import CertificationFormSet, TrainerApplicationForm
from .models import TrainerApplication
from .storage import save_certification_upload


def _get_application(user):
    return TrainerApplication.objects.filter(user=user).first()


@login_required
def application_form(request):
    application = _get_application(request.user)
    if application and application.status != TrainerApplication.Status.REJECTED:
        return redirect("trainers:application_status")

    if request.method == "POST":
        form = TrainerApplicationForm(request.POST, instance=application)
        formset = CertificationFormSet(
            request.POST,
            request.FILES,
            instance=application,
            prefix="certifications",
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                application = form.save(commit=False)
                application.user = request.user
                application.status = TrainerApplication.Status.PENDING
                application.rejection_reason = ""
                application.reviewed_by = None
                application.reviewed_at = None
                application.submitted_at = timezone.now()
                application.save()

                for certification_form in formset.forms:
                    if not certification_form.cleaned_data:
                        continue
                    if certification_form.cleaned_data.get("DELETE"):
                        if certification_form.instance.pk:
                            certification_form.instance.delete()
                        continue

                    certification = certification_form.save(commit=False)
                    uploaded_file = certification_form.cleaned_data.get("evidence_file")
                    if uploaded_file:
                        object_key, original_filename = save_certification_upload(
                            uploaded_file=uploaded_file,
                            user_id=request.user.pk,
                        )
                        certification.evidence_object_key = object_key
                        certification.original_filename = original_filename
                    certification.application = application
                    certification.save()

            messages.success(request, "트레이너 인증 신청이 제출되었습니다.")
            return redirect("trainers:application_status")
    else:
        form = TrainerApplicationForm(instance=application)
        formset = CertificationFormSet(instance=application, prefix="certifications")

    return render(
        request,
        "trainers/application_form.html",
        {"form": form, "formset": formset, "application": application},
    )


@login_required
def application_status(request):
    application = _get_application(request.user)
    if not application:
        return redirect("trainers:application_form")
    return render(
        request,
        "trainers/application_status.html",
        {"application": application},
    )
