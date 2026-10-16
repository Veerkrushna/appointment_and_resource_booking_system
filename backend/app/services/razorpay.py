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


class RazorpayRefundRejectedError(RazorpayIntegrationError):
    """Raised when Razorpay definitively rejects a refund request."""


class RazorpayRefundNotSubmittedError(RazorpayIntegrationError):
    """Raised when a refund request was not sent to Razorpay."""


class RazorpayRefundOutcomeUnknownError(RazorpayIntegrationError):
    """Raised when a refund request may have reached Razorpay."""


class RazorpayService:
    def __init__(self, client: razorpay.Client | None = None) -> None:
        self._api_credentials_configured = (
            settings.razorpay_key_id is not None
            and settings.razorpay_key_secret is not None
        )
        if client is not None:
            self._client = client
            self._api_credentials_configured = True
            return

        self._client = razorpay.Client(
            auth=(
                settings.razorpay_key_id or "",
                (
                    settings.razorpay_key_secret.get_secret_value()
                    if settings.razorpay_key_secret is not None
                    else ""
                ),
            )
        )

    def create_order(
        self, amount: int, receipt: str, currency: str = "INR"
    ) -> dict[str, Any]:
        if not self._api_credentials_configured:
            raise RazorpayIntegrationError("Razorpay credentials are not configured")
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

    def verify_payment(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
        *,
        expected_amount: int,
        expected_currency: str,
    ) -> bool:
        if not self._api_credentials_configured:
            raise RazorpayIntegrationError("Razorpay credentials are not configured")
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

        amount = payment.get("amount")
        return (
            payment.get("order_id") == order_id
            and payment.get("status") == "captured"
            and type(amount) is int
            and amount == expected_amount
            and payment.get("currency") == expected_currency
        )

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        if not self._api_credentials_configured:
            raise RazorpayIntegrationError("Razorpay credentials are not configured")
        try:
            return self._client.payment.fetch(payment_id)
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ):
            raise RazorpayIntegrationError("Razorpay payment fetch failed") from None

    def create_full_refund(
        self, payment_id: str, amount: int, idempotency_key: str
    ) -> dict[str, Any]:
        if not self._api_credentials_configured:
            raise RazorpayRefundNotSubmittedError(
                "Razorpay credentials are not configured"
            )
        try:
            return self._client.payment.refund(
                payment_id,
                amount,
                headers={"X-Refund-Idempotency": idempotency_key},
            )
        except BadRequestError:
            raise RazorpayRefundRejectedError(
                "Razorpay refund request was rejected"
            ) from None
        except (
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ):
            raise RazorpayRefundOutcomeUnknownError(
                "Razorpay refund outcome is unknown"
            ) from None

    def fetch_refund(self, payment_id: str, refund_id: str) -> dict[str, Any]:
        if not self._api_credentials_configured:
            raise RazorpayIntegrationError("Razorpay credentials are not configured")
        try:
            return self._client.payment.fetch_refund_id(payment_id, refund_id)
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ):
            raise RazorpayIntegrationError("Razorpay refund lookup failed") from None

    def fetch_payment_refunds(self, payment_id: str) -> dict[str, Any]:
        if not self._api_credentials_configured:
            raise RazorpayIntegrationError("Razorpay credentials are not configured")
        try:
            return self._client.payment.fetch_multiple_refund(payment_id)
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ):
            raise RazorpayIntegrationError("Razorpay refund lookup failed") from None

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        webhook_secret = settings.razorpay_webhook_secret
        if webhook_secret is None:
            raise RazorpayIntegrationError("Razorpay webhook secret is not configured")
        try:
            body = raw_body.decode("utf-8")
            return self._client.utility.verify_webhook_signature(
                body, signature, webhook_secret.get_secret_value()
            )
        except (SignatureVerificationError, UnicodeDecodeError):
            return False
