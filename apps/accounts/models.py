from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("이메일은 필수입니다.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("슈퍼유저는 is_staff=True여야 합니다.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("슈퍼유저는 is_superuser=True여야 합니다.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = "MEMBER", "일반회원"
        TRAINER = "TRAINER", "트레이너"

    username = None
    email = models.EmailField("이메일", unique=True)
    full_name = models.CharField("이름", max_length=100)
    nickname = models.CharField("닉네임", max_length=50, unique=True)
    email_verified_at = models.DateTimeField("이메일 인증시각", null=True, blank=True)
    role = models.CharField(
        "역할", max_length=20, choices=Role.choices, default=Role.MEMBER
    )
    created_at = models.DateTimeField("생성시각", auto_now_add=True)
    updated_at = models.DateTimeField("수정시각", auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name", "nickname"]

    objects = UserManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "회원"
        verbose_name_plural = "회원"

    def __str__(self):
        return f"{self.nickname} ({self.email})"

    @property
    def is_email_verified(self):
        return self.email_verified_at is not None
