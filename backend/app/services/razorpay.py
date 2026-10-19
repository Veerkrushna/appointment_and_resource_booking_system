import json
import logging
import re
from typing import Any, NoReturn

import razorpay
import requests
from razorpay.errors import (
    BadRequestError,
    GatewayError,
    ServerError,
    SignatureVerificationError,
)
from requests import Response

from app.core.config import settings

logger = logging.getLogger(__name__)
_JSON_CONTENT_TYPE = re.compile(r"application/(?:[a-z0-9.+-]+\+)?json\Z")


class RazorpayIntegrationError(RuntimeError):
    """Raised when Razorpay order creation fails."""


class RazorpayRefundRejectedError(RazorpayIntegrationError):
    """Raised when Razorpay definitively rejects a refund request."""


class RazorpayRefundNotSubmittedError(RazorpayIntegrationError):
    """Raised when a refund request was not sent to Razorpay."""


class RazorpayRefundOutcomeUnknownError(RazorpayIntegrationError):
    """Raised when a refund request may have reached Razorpay."""

    def __init__(self, message: str, *, failure_classification: str = "unknown"):
        super().__init__(message)
        self.failure_classification = failure_classification


class RazorpayLookupError(RazorpayIntegrationError):
    """Raised when a read-only Razorpay lookup cannot provide usable evidence."""

    def __init__(
        self,
        message: str,
        *,
        failure_classification: str,
        provider_http_status: int | None = None,
    ):
        super().__init__(message)
        self.failure_classification = failure_classification
        self.provider_http_status = provider_http_status


def _capture_response_metadata(
    response: Response, diagnostics: dict[str, Any]
) -> Response:
    content_type = response.headers.get("Content-Type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    sanitized_content_type = (
        media_type
        if _JSON_CONTENT_TYPE.fullmatch(media_type)
        else "other"
        if media_type
        else "missing"
    )
    body = response.content
    if not body:
        response_summary = "empty_body"
    else:
        try:
            parsed_body = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            response_summary = "invalid_json"
        else:
            if isinstance(parsed_body, dict):
                response_summary = "json_object"
            elif isinstance(parsed_body, list):
                response_summary = "json_array"
            else:
                response_summary = "json_scalar"

    diagnostics.update(
        {
            "provider_http_status": response.status_code,
            "provider_content_type": sanitized_content_type,
            "provider_response_summary": response_summary,
            "provider_response_bytes": len(body),
        }
    )
    return response


def _lookup_failure(
    operation: str, diagnostics: dict[str, Any], error: Exception
) -> RazorpayLookupError:
    provider_status = diagnostics.get("provider_http_status")
    if provider_status == 404 and operation == "refund":
        classification = "refund_not_found"
        reason = (
            "Razorpay did not find the refund for the supplied payment and refund IDs."
        )
    elif isinstance(provider_status, int) and 400 <= provider_status < 500:
        classification = "provider_rejected_lookup"
        reason = f"Razorpay rejected the {operation} lookup (HTTP {provider_status})."
    elif isinstance(provider_status, int) and provider_status >= 500:
        classification = "provider_server_error"
        reason = f"Razorpay returned a server error for the {operation} lookup (HTTP {provider_status})."
    elif isinstance(provider_status, int) and 200 <= provider_status < 300:
        classification = "invalid_provider_response"
        reason = (
            f"Razorpay returned an unreadable response for the {operation} lookup "
            f"(HTTP {provider_status})."
        )
    elif isinstance(error, BadRequestError):
        classification = "provider_rejected_lookup"
        reason = f"Razorpay rejected the {operation} lookup."
    elif isinstance(error, ServerError):
        classification = "provider_server_error"
        reason = f"Razorpay returned a server error for the {operation} lookup."
    elif isinstance(error, GatewayError):
        classification = "provider_gateway_error"
        reason = f"Razorpay's gateway could not complete the {operation} lookup."
    elif provider_status is not None:
        classification = "provider_response_error"
        reason = f"Razorpay returned an unexpected response for the {operation} lookup."
    else:
        classification = "transport_error"
        reason = f"Razorpay {operation} lookup could not reach the provider."
    return RazorpayLookupError(
        reason,
        failure_classification=classification,
        provider_http_status=(
            provider_status if isinstance(provider_status, int) else None
        ),
    )


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
        diagnostics: dict[str, Any] = {}
        try:
            return self._client.payment.fetch(
                payment_id,
                hooks={
                    "response": [
                        lambda response, *args, **kwargs: _capture_response_metadata(
                            response, diagnostics
                        )
                    ]
                },
            )
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ) as error:
            lookup_error = _lookup_failure("payment", diagnostics, error)
            logger.warning(
                "Razorpay payment lookup failed",
                extra={
                    "provider_operation": "payment_lookup",
                    "failure_classification": lookup_error.failure_classification,
                    "provider_http_status": lookup_error.provider_http_status,
                    **diagnostics,
                },
            )
            raise lookup_error from error

    def create_full_refund(
        self, payment_id: str, amount: int, idempotency_key: str
    ) -> dict[str, Any]:
        if not self._api_credentials_configured:
            raise RazorpayRefundNotSubmittedError(
                "Razorpay credentials are not configured"
            )
        logger.info(
            "Razorpay refund request started",
            extra={
                "refund_event": "request_started",
                "provider_payment_id": payment_id,
                "amount": amount,
            },
        )
        response_diagnostics: dict[str, Any] = {}

        def capture_response(response: Response, *args, **kwargs) -> Response:
            content_type = response.headers.get("Content-Type", "")
            media_type = content_type.split(";", 1)[0].strip().lower()
            sanitized_content_type = (
                media_type
                if _JSON_CONTENT_TYPE.fullmatch(media_type)
                else "other"
                if media_type
                else "missing"
            )
            body = response.content
            if not body:
                response_summary = "empty_body"
            else:
                try:
                    parsed_body = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response_summary = "invalid_json"
                else:
                    if isinstance(parsed_body, dict):
                        response_summary = "json_object"
                    elif isinstance(parsed_body, list):
                        response_summary = "json_array"
                    else:
                        response_summary = "json_scalar"

            response_diagnostics.update(
                {
                    "provider_http_status": response.status_code,
                    "provider_content_type": sanitized_content_type,
                    "provider_response_summary": response_summary,
                    "provider_response_bytes": len(body),
                }
            )
            return response

        def log_failure(failure_classification: str) -> None:
            logger.warning(
                "Razorpay refund request failed",
                extra={
                    "refund_event": "request_failed",
                    "provider_payment_id": payment_id,
                    "amount": amount,
                    "failure_classification": failure_classification,
                    "provider_refund_id_returned": False,
                    **response_diagnostics,
                },
            )

        def raise_rejected() -> NoReturn:
            log_failure("definitive_rejection")
            raise RazorpayRefundRejectedError(
                "Razorpay refund request was rejected"
            ) from None

        try:
            result = self._client.payment.refund(
                payment_id,
                {"amount": amount},
                headers={"X-Refund-Idempotency": idempotency_key},
                hooks={"response": [capture_response]},
            )
            provider_status = result.get("status") if isinstance(result, dict) else None
            logger.info(
                "Razorpay refund response received",
                extra={
                    "refund_event": "response_received",
                    "provider_payment_id": payment_id,
                    "amount": amount,
                    "provider_response_status": (
                        provider_status if isinstance(provider_status, str) else None
                    ),
                    "provider_http_status": None,
                    **response_diagnostics,
                    "provider_refund_id_returned": (
                        isinstance(result, dict)
                        and isinstance(result.get("id"), str)
                        and bool(result["id"])
                    ),
                    "failure_classification": None,
                },
            )
            return result
        except BadRequestError:
            raise_rejected()
        except requests.exceptions.Timeout:
            failure_classification = "timeout"
            log_failure(failure_classification)
            raise RazorpayRefundOutcomeUnknownError(
                "Razorpay refund outcome is unknown",
                failure_classification=failure_classification,
            ) from None
        except (
            ServerError,
            GatewayError,
            requests.exceptions.RequestException,
        ) as error:
            provider_http_status = response_diagnostics.get("provider_http_status")
            if (
                isinstance(provider_http_status, int)
                and 400 <= provider_http_status < 500
            ):
                raise_rejected()
            if isinstance(error, ServerError) or (
                isinstance(provider_http_status, int) and provider_http_status >= 500
            ):
                failure_classification = "server_error"
            elif isinstance(error, GatewayError):
                failure_classification = "gateway_error"
            elif (
                isinstance(provider_http_status, int)
                and 200 <= provider_http_status < 300
            ):
                failure_classification = "invalid_provider_response"
            elif provider_http_status is not None:
                failure_classification = "provider_response_error"
            else:
                failure_classification = "transport_error"
            log_failure(failure_classification)
            raise RazorpayRefundOutcomeUnknownError(
                "Razorpay refund outcome is unknown",
                failure_classification=failure_classification,
            ) from None

    def fetch_refund(self, payment_id: str, refund_id: str) -> dict[str, Any]:
        if not self._api_credentials_configured:
            raise RazorpayIntegrationError("Razorpay credentials are not configured")
        diagnostics: dict[str, Any] = {}
        try:
            return self._client.payment.fetch_refund_id(
                payment_id,
                refund_id,
                hooks={
                    "response": [
                        lambda response, *args, **kwargs: _capture_response_metadata(
                            response, diagnostics
                        )
                    ]
                },
            )
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ) as error:
            lookup_error = _lookup_failure("refund", diagnostics, error)
            logger.warning(
                "Razorpay refund lookup failed",
                extra={
                    "provider_operation": "refund_lookup",
                    "provider_payment_id": payment_id,
                    "provider_refund_id_present": bool(refund_id),
                    "failure_classification": lookup_error.failure_classification,
                    "provider_http_status": lookup_error.provider_http_status,
                    **diagnostics,
                },
            )
            raise lookup_error from error

    def fetch_payment_refunds(self, payment_id: str) -> dict[str, Any]:
        if not self._api_credentials_configured:
            raise RazorpayIntegrationError("Razorpay credentials are not configured")
        diagnostics: dict[str, Any] = {}
        try:
            return self._client.payment.fetch_multiple_refund(
                payment_id,
                hooks={
                    "response": [
                        lambda response, *args, **kwargs: _capture_response_metadata(
                            response, diagnostics
                        )
                    ]
                },
            )
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            requests.exceptions.RequestException,
        ) as error:
            lookup_error = _lookup_failure("refund history", diagnostics, error)
            logger.warning(
                "Razorpay refund history lookup failed",
                extra={
                    "provider_operation": "refund_history_lookup",
                    "provider_payment_id_present": bool(payment_id),
                    "failure_classification": lookup_error.failure_classification,
                    "provider_http_status": lookup_error.provider_http_status,
                    **diagnostics,
                },
            )
            raise lookup_error from error

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
