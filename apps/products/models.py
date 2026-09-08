from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField("카테고리명", max_length=80, unique=True)
    slug = models.SlugField("슬러그", max_length=100, unique=True)
    description = models.TextField("설명", blank=True)
    is_active = models.BooleanField("활성 여부", default=True)
    sort_order = models.IntegerField("표시 순서", default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "운동 카테고리"
        verbose_name_plural = "운동 카테고리"

    def __str__(self):
        return self.name


class ExerciseGoal(models.Model):
    name = models.CharField("운동 목적", max_length=80, unique=True)
    slug = models.SlugField("슬러그", max_length=100, unique=True)
    is_active = models.BooleanField("활성 여부", default=True)
    sort_order = models.IntegerField("표시 순서", default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "운동 목적"
        verbose_name_plural = "운동 목적"

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class Difficulty(models.TextChoices):
        BEGINNER = "BEGINNER", "초급"
        INTERMEDIATE = "INTERMEDIATE", "중급"
        ADVANCED = "ADVANCED", "고급"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "작성 중"
        PUBLISHED = "PUBLISHED", "판매 중"
        SUSPENDED = "SUSPENDED", "판매 중지"

    seller = models.ForeignKey(
        "trainers.TrainerProfile",
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="판매자",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="카테고리",
    )
    goals = models.ManyToManyField(
        ExerciseGoal,
        through="ProductGoal",
        related_name="products",
        verbose_name="운동 목적",
    )
    title = models.CharField("상품명", max_length=200)
    slug = models.SlugField("슬러그", max_length=220, unique=True, allow_unicode=True)
    short_description = models.CharField("요약", max_length=300)
    description = models.TextField("상세 설명")
    difficulty = models.CharField("난이도", max_length=20, choices=Difficulty.choices)
    duration_weeks = models.PositiveSmallIntegerField("기간(주)")
    sessions_per_week = models.PositiveSmallIntegerField("주당 운동 횟수")
    price = models.PositiveIntegerField("가격", default=0)
    thumbnail_object_key = models.CharField("썸네일 객체 키", max_length=500)
    status = models.CharField(
        "판매 상태", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    published_at = models.DateTimeField("최초 공개시각", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "운동 루틴 상품"
        verbose_name_plural = "운동 루틴 상품"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["category", "difficulty", "price"]),
            models.Index(fields=["seller", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_weeks__gte=1), name="product_duration_at_least_one"
            ),
            models.CheckConstraint(
                condition=Q(sessions_per_week__gte=1) & Q(sessions_per_week__lte=14),
                name="product_sessions_between_1_and_14",
            ),
            models.CheckConstraint(condition=Q(price__gte=0), name="product_price_nonnegative"),
        ]

    def clean(self):
        errors = {}
        if self.status == self.Status.PUBLISHED and self.seller_id:
            if not self.seller.is_verified or not self.seller.user.is_active:
                errors["status"] = "인증된 활성 트레이너만 상품을 공개할 수 있습니다."
            if self.pk and not self.files.filter(is_current=True).exists():
                errors["status"] = "현재 판매할 운동 루틴 파일이 필요합니다."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title

    @property
    def thumbnail_url(self):
        return default_storage.url(self.thumbnail_object_key)


class ProductGoal(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    goal = models.ForeignKey(ExerciseGoal, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "상품 운동 목적"
        verbose_name_plural = "상품 운동 목적"
        constraints = [
            models.UniqueConstraint(fields=["product", "goal"], name="uniq_product_goal")
        ]


class ProductFile(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="files", verbose_name="상품"
    )
    version = models.PositiveIntegerField("버전")
    object_key = models.CharField("S3 객체 키", max_length=500, unique=True)
    original_filename = models.CharField("원본 파일명", max_length=255)
    content_type = models.CharField("MIME 유형", max_length=100)
    size_bytes = models.PositiveBigIntegerField("파일 크기")
    checksum_sha256 = models.CharField("SHA-256", max_length=64)
    is_current = models.BooleanField("현재 버전", default=True)
    created_at = models.DateTimeField("업로드시각", auto_now_add=True)

    class Meta:
        ordering = ["product", "-version"]
        verbose_name = "운동 루틴 파일"
        verbose_name_plural = "운동 루틴 파일"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "version"], name="uniq_product_file_version"
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_current=True),
                name="uniq_current_product_file",
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1), name="product_file_version_at_least_one"
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__gte=1), name="product_file_size_positive"
            ),
        ]

    def __str__(self):
        return f"{self.product.title} v{self.version}"


class WishlistItem(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name="회원",
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="wishlist_items", verbose_name="상품"
    )
    created_at = models.DateTimeField("찜한 시각", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "찜"
        verbose_name_plural = "찜"
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="uniq_user_wishlist_product")
        ]

    def __str__(self):
        return f"{self.user.nickname} - {self.product.title}"
