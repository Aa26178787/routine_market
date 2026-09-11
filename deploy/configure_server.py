"""Configure the production database role and systemd environment on EC2."""

import json
import os
import secrets
from pathlib import Path

import boto3
import psycopg
from psycopg import sql


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


region = required("DEPLOY_AWS_REGION")
db_host = required("DEPLOY_DB_HOST")
master_secret_arn = required("DEPLOY_MASTER_SECRET_ARN")
app_secret_arn = required("DEPLOY_APP_SECRET_ARN")
public_host = required("DEPLOY_PUBLIC_HOST")

client = boto3.client("secretsmanager", region_name=region)
master_secret = json.loads(
    client.get_secret_value(SecretId=master_secret_arn)["SecretString"]
)
app_secret = json.loads(
    client.get_secret_value(SecretId=app_secret_arn)["SecretString"]
)

db_name = app_secret["dbname"]
app_user = app_secret["username"]
app_password = app_secret["password"]

with psycopg.connect(
    host=db_host,
    port=5432,
    dbname=db_name,
    user=master_secret["username"],
    password=master_secret["password"],
    sslmode="require",
    autocommit=True,
) as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (app_user,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(app_user),
                    sql.Literal(app_password),
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(app_user),
                    sql.Literal(app_password),
                )
            )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(db_name),
                sql.Identifier(app_user),
            )
        )
        cursor.execute(
            sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                sql.Identifier(app_user)
            )
        )

environment = {
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "DJANGO_DEBUG": "false",
    "DJANGO_ALLOWED_HOSTS": f"{public_host},localhost,127.0.0.1",
    "DJANGO_CSRF_TRUSTED_ORIGINS": f"http://{public_host}",
    "DJANGO_SECURE_SSL_REDIRECT": "false",
    "DJANGO_SECURE_HSTS_SECONDS": "0",
    "DJANGO_SESSION_COOKIE_SECURE": "false",
    "DJANGO_CSRF_COOKIE_SECURE": "false",
    "DJANGO_LOG_LEVEL": "INFO",
    "DB_ENGINE": "postgresql",
    "DB_NAME": db_name,
    "DB_USER": app_user,
    "DB_PASSWORD": app_password,
    "DB_HOST": db_host,
    "DB_PORT": "5432",
    "DB_SSLMODE": "require",
    "USE_S3": "true",
    "AWS_STORAGE_BUCKET_NAME": "routine-market-108327566686-ap-northeast-2",
    "AWS_S3_REGION_NAME": region,
    "AWS_MEDIA_LOCATION": "media",
    "PRIVATE_FILE_DELIVERY": "redirect",
    "DOWNLOAD_URL_EXPIRES": "300",
}

environment_path = Path("/etc/routine-market.env")
environment_path.write_text(
    "".join(f"{name}={value}\n" for name, value in environment.items()),
    encoding="utf-8",
)
environment_path.chmod(0o600)
print("Database role and protected environment file configured.")
