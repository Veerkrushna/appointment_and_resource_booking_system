from typing import Any

import razorpay
import requests
from razorpay.errors import (
    BadRequestError,
    GatewayError,
    ServerError,
    SignatureVerificationError,
)

from app.core.config import settings


class RazorpayIntegrationError(RuntimeError):
    """Raised when Razorpay order creation fails."""


class RazorpayService:
    def __init__(self, client: razorpay.Client | None = None) -> None:
        if client is not None:
            self._client = client
            return

        if settings.razorpay_key_id is None or settings.razorpay_key_secret is None:
            raise RazorpayIntegrationError("Razorpay credentials are not configured")

        self._client = razorpay.Client(
            auth=(
                settings.razorpay_key_id,
                settings.razorpay_key_secret.get_secret_value(),
            )
        )

    def create_order(
        self, amount: int, receipt: str, currency: str = "INR"
    ) -> dict[str, Any]:
        try:
            return self._client.order.create(
                {"amount": amount, "currency": currency, "receipt": receipt}
            )
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ):
            raise RazorpayIntegrationError("Razorpay order creation failed") from None

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        try:
            signature_valid = self._client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
        except SignatureVerificationError:
            return False
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ):
            raise RazorpayIntegrationError(
                "Razorpay payment verification failed"
            ) from None

        if not signature_valid:
            return False

        try:
            payment = self._client.payment.fetch(payment_id)
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ):
            raise RazorpayIntegrationError(
                "Razorpay payment verification failed"
            ) from None

        return (
            payment.get("order_id") == order_id and payment.get("status") == "captured"
        )
