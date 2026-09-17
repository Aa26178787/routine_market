import base64
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


@dataclass
class TossPaymentsError(Exception):
    code: str
    public_message: str

    def __str__(self):
        return self.public_message


class TossPaymentsClient:
    def __init__(self):
        self.secret_key = settings.TOSS_PAYMENTS_SECRET_KEY
        self.base_url = settings.TOSS_PAYMENTS_API_BASE_URL
        self.timeout = settings.TOSS_PAYMENTS_TIMEOUT

    def confirm(self, *, payment_key: str, order_id: str, amount: int) -> dict:
        if not self.secret_key:
            raise TossPaymentsError(
                "PAYMENT_NOT_CONFIGURED",
                "결제 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요.",
            )

        credentials = base64.b64encode(f"{self.secret_key}:".encode()).decode()
        body = json.dumps(
            {"paymentKey": payment_key, "orderId": order_id, "amount": amount}
        ).encode()
        request = Request(
            f"{self.base_url}/v1/payments/confirm",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
                "Idempotency-Key": f"routine-market-confirm-{order_id}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode())
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            raise TossPaymentsError(
                str(payload.get("code") or "PAYMENT_CONFIRM_FAILED"),
                "결제를 승인하지 못했습니다. 결제 정보를 확인한 뒤 다시 시도해 주세요.",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TossPaymentsError(
                "PAYMENT_SERVICE_UNAVAILABLE",
                "결제 서비스 연결이 원활하지 않습니다. 잠시 후 다시 시도해 주세요.",
            ) from exc
