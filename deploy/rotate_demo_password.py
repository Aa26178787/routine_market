"""Rotate deployed demo-account passwords from an AWS Secrets Manager secret."""

import json
import os

import boto3
import django


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402


secret_arn = os.environ["DEMO_LOGIN_SECRET_ARN"]
region = os.environ.get("AWS_S3_REGION_NAME", "ap-northeast-2")
secret = boto3.client("secretsmanager", region_name=region).get_secret_value(
    SecretId=secret_arn
)
password = json.loads(secret["SecretString"])["password"]

users = get_user_model().objects.filter(email__endswith="@routine-market.local")
updated = 0
for user in users:
    user.set_password(password)
    user.save(update_fields=["password"])
    updated += 1

print(f"Rotated {updated} production demo account passwords.")
