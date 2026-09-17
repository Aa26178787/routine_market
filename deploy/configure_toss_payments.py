"""Load Toss Payments keys from Secrets Manager into the protected service env file."""

import json
import os
from pathlib import Path

import boto3


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


region = os.environ.get("AWS_S3_REGION_NAME", "ap-northeast-2")
secret_arn = required("TOSS_PAYMENTS_SECRET_ARN")
payload = json.loads(
    boto3.client("secretsmanager", region_name=region)
    .get_secret_value(SecretId=secret_arn)["SecretString"]
)
client_key = str(payload.get("client_key") or "").strip()
secret_key = str(payload.get("secret_key") or "").strip()

valid_pairs = (
    ("test_gck_", "test_gsk_"),
    ("live_gck_", "live_gsk_"),
    ("test_ck_", "test_sk_"),
    ("live_ck_", "live_sk_"),
)
if not any(client_key.startswith(client) and secret_key.startswith(secret) for client, secret in valid_pairs):
    raise RuntimeError("Toss Payments client and secret keys are not a matching pair")

environment_path = Path("/etc/routine-market.env")
environment = {}
for line in environment_path.read_text(encoding="utf-8").splitlines():
    name, separator, value = line.partition("=")
    if separator:
        environment[name] = value

environment["TOSS_PAYMENTS_CLIENT_KEY"] = client_key
environment["TOSS_PAYMENTS_SECRET_KEY"] = secret_key
environment["TOSS_PAYMENTS_API_BASE_URL"] = "https://api.tosspayments.com"
environment["TOSS_PAYMENTS_TIMEOUT"] = "10"

environment_path.write_text(
    "".join(f"{name}={value}\n" for name, value in environment.items()),
    encoding="utf-8",
)
environment_path.chmod(0o600)
print("Toss Payments settings configured.")
