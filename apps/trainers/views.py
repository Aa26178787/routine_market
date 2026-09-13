from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import CertificationFormSet, TrainerApplicationForm, TrainerProfileForm
from .models import TrainerApplication, TrainerProfile
from .storage import delete_certification_upload, save_certification_upload


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
            uploaded_keys = []
            try:
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
                            uploaded_keys.append(object_key)
                            certification.evidence_object_key = object_key
                            certification.original_filename = original_filename
                        certification.application = application
                        certification.save()
            except Exception:
                for object_key in uploaded_keys:
                    delete_certification_upload(object_key)
                raise

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


@login_required
def trainer_profile_update(request):
    if request.user.role != request.user.Role.TRAINER:
        raise PermissionDenied("승인된 트레이너만 프로필을 수정할 수 있습니다.")

    trainer = get_object_or_404(
        TrainerProfile,
        user=request.user,
        is_verified=True,
    )
    if request.method == "POST":
        form = TrainerProfileForm(request.POST, instance=trainer)
        if form.is_valid():
            form.save()
            messages.success(request, "트레이너 프로필이 수정되었습니다.")
            return redirect("trainers:detail", pk=trainer.pk)
    else:
        form = TrainerProfileForm(instance=trainer)
    return render(
        request,
        "trainers/trainer_profile_form.html",
        {"form": form, "trainer": trainer},
    )


def trainer_detail(request, pk):
    trainer = get_object_or_404(
        TrainerProfile.objects.select_related("user"),
        pk=pk,
        is_verified=True,
        user__is_active=True,
    )
    products = (
        trainer.products.filter(status="PUBLISHED")
        .select_related("seller__user", "category")
        .annotate(
            average_rating=Avg("reviews__rating", filter=Q(reviews__is_visible=True)),
            review_count=Count(
                "reviews", filter=Q(reviews__is_visible=True), distinct=True
            ),
        )
        .order_by("-published_at", "-created_at")
    )
    sales = trainer.order_items.filter(order__status="PAID").aggregate(
        sales_count=Count("id")
    )
    return render(
        request,
        "trainers/trainer_detail.html",
        {
            "trainer": trainer,
            "products": products,
            "product_count": products.count(),
            "sales_count": sales["sales_count"],
        },
    )
