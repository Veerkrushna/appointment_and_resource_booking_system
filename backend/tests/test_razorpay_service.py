import json
from unittest.mock import MagicMock

import pytest
import razorpay
import requests
from pydantic import SecretStr
from razorpay.errors import (
    BadRequestError,
    GatewayError,
    ServerError,
    SignatureVerificationError,
)
from requests import Response

from app.core.config import Settings
from app.services.razorpay import (
    RazorpayIntegrationError,
    RazorpayLookupError,
    RazorpayRefundNotSubmittedError,
    RazorpayRefundOutcomeUnknownError,
    RazorpayRefundRejectedError,
    RazorpayService,
)


def test_create_order_sends_amount_currency_and_receipt():
    client = MagicMock()
    expected_order = {"id": "order_test", "amount": 50000}
    client.order.create.return_value = expected_order
    service = RazorpayService(client=client)

    result = service.create_order(amount=50000, receipt="booking-receipt")

    assert result == expected_order
    client.order.create.assert_called_once_with(
        {"amount": 50000, "currency": "INR", "receipt": "booking-receipt"}
    )


def test_verify_payment_checks_signature_and_captured_payment_order():
    client = MagicMock()
    client.utility.verify_payment_signature.return_value = True
    client.payment.fetch.return_value = {
        "order_id": "order_test",
        "status": "captured",
        "amount": 2510,
        "currency": "INR",
    }
    service = RazorpayService(client=client)

    assert service.verify_payment(
        "order_test",
        "pay_test",
        "signature_test",
        expected_amount=2510,
        expected_currency="INR",
    )
    client.utility.verify_payment_signature.assert_called_once_with(
        {
            "razorpay_order_id": "order_test",
            "razorpay_payment_id": "pay_test",
            "razorpay_signature": "signature_test",
        }
    )
    client.payment.fetch.assert_called_once_with("pay_test")


def test_verify_payment_rejects_invalid_signature_without_fetching_payment():
    client = MagicMock()
    client.utility.verify_payment_signature.return_value = False
    service = RazorpayService(client=client)

    assert not service.verify_payment(
        "order_test",
        "pay_test",
        "invalid",
        expected_amount=2510,
        expected_currency="INR",
    )
    client.payment.fetch.assert_not_called()


def test_fetch_payment_returns_authenticated_client_payment():
    client = MagicMock()
    payment = {"id": "pay_test", "status": "captured"}
    client.payment.fetch.return_value = payment
    service = RazorpayService(client=client)

    assert service.fetch_payment("pay_test") == payment
    client.payment.fetch.assert_called_once()
    assert client.payment.fetch.call_args.args == ("pay_test",)
    assert len(client.payment.fetch.call_args.kwargs["hooks"]["response"]) == 1


def test_create_full_refund_uses_sdk_payment_refund_api(caplog):
    caplog.set_level("INFO")
    client = MagicMock()
    refund = {"id": "rfnd_test", "status": "processed"}
    client.payment.refund.return_value = refund
    service = RazorpayService(client=client)

    assert service.create_full_refund("pay_test", 2510, "refund-key-123") == refund
    client.payment.refund.assert_called_once()
    args, kwargs = client.payment.refund.call_args
    assert args == ("pay_test", {"amount": 2510})
    assert kwargs["headers"] == {"X-Refund-Idempotency": "refund-key-123"}
    assert len(kwargs["hooks"]["response"]) == 1
    response_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "response_received"
    )
    assert response_log.provider_payment_id == "pay_test"
    assert response_log.amount == 2510
    assert response_log.provider_response_status == "processed"
    assert response_log.provider_refund_id_returned is True


def _sdk_client_with_response(monkeypatch, status_code, body, content_type=None):
    client = razorpay.Client(auth=("test-key-id", "test-key-secret"))
    adapter = client.session.get_adapter("https://")
    sent_requests = []

    def send(prepared_request, **kwargs):
        sent_requests.append(prepared_request)
        response = Response()
        response.status_code = status_code
        response._content = body
        response.request = prepared_request
        response.url = prepared_request.url
        if content_type is not None:
            response.headers["Content-Type"] = content_type
        return response

    monkeypatch.setattr(adapter, "send", send)
    return client, sent_requests


def test_sdk_refund_uses_correct_endpoint_auth_payload_and_idempotency_header(
    monkeypatch, caplog
):
    caplog.set_level("INFO")
    body = json.dumps(
        {
            "id": "rfnd_test",
            "payment_id": "pay_test",
            "amount": 2510,
            "currency": "INR",
            "status": "processed",
        }
    ).encode()
    client, sent_requests = _sdk_client_with_response(
        monkeypatch, 200, body, "application/json"
    )
    service = RazorpayService(client=client)

    result = service.create_full_refund("pay_test", 2510, "refund-key-123")

    assert result["id"] == "rfnd_test"
    assert len(sent_requests) == 1
    request = sent_requests[0]
    assert request.method == "POST"
    assert request.url == "https://api.razorpay.com/v1/payments/pay_test/refund"
    assert request.body == '{"amount": 2510}'
    assert request.headers["Authorization"].startswith("Basic ")
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["X-Refund-Idempotency"] == "refund-key-123"
    assert "test-key-secret" not in caplog.text
    assert "refund-key-123" not in caplog.text
    response_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "response_received"
    )
    assert response_log.provider_http_status == 200
    assert response_log.provider_content_type == "application/json"
    assert response_log.provider_response_summary == "json_object"


@pytest.mark.parametrize(
    ("status_code", "body", "content_type", "expected_classification", "summary"),
    [
        (200, b"", None, "invalid_provider_response", "empty_body"),
        (
            200,
            b"<html>private upstream body</html>",
            "text/html",
            "invalid_provider_response",
            "invalid_json",
        ),
        (
            400,
            b"<html>private rejection body</html>",
            "text/html",
            "definitive_rejection",
            "invalid_json",
        ),
    ],
)
def test_sdk_non_json_refund_response_is_safely_classified(
    monkeypatch,
    caplog,
    status_code,
    body,
    content_type,
    expected_classification,
    summary,
):
    client, _ = _sdk_client_with_response(monkeypatch, status_code, body, content_type)
    service = RazorpayService(client=client)

    expected_error = (
        RazorpayRefundRejectedError
        if expected_classification == "definitive_rejection"
        else RazorpayRefundOutcomeUnknownError
    )
    with pytest.raises(expected_error) as error:
        service.create_full_refund("pay_test", 2510, "refund-key-123")

    failure_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "request_failed"
    )
    assert failure_log.provider_http_status == status_code
    assert failure_log.provider_response_summary == summary
    assert failure_log.failure_classification == expected_classification
    assert "private upstream body" not in caplog.text
    assert "private rejection body" not in caplog.text
    assert "refund-key-123" not in caplog.text
    if expected_classification == "invalid_provider_response":
        assert error.value.failure_classification == expected_classification


@pytest.mark.parametrize(
    ("status_code", "body", "content_type", "classification", "message"),
    [
        (
            404,
            b'{"error":{"description":"private not found details"}}',
            "application/json",
            "refund_not_found",
            "did not find the refund",
        ),
        (
            200,
            b"",
            None,
            "invalid_provider_response",
            "unreadable response",
        ),
        (
            502,
            b"<html>private upstream details</html>",
            "text/html",
            "provider_server_error",
            "server error",
        ),
    ],
)
def test_fetch_refund_lookup_reports_safe_provider_classification(
    monkeypatch,
    caplog,
    status_code,
    body,
    content_type,
    classification,
    message,
):
    client, sent_requests = _sdk_client_with_response(
        monkeypatch, status_code, body, content_type
    )
    service = RazorpayService(client=client)

    with pytest.raises(RazorpayLookupError) as error:
        service.fetch_refund("pay_test", "rfnd_test")

    assert error.value.failure_classification == classification
    assert error.value.provider_http_status == status_code
    assert error.value.__cause__ is not None
    assert message in str(error.value)
    assert len(sent_requests) == 1
    assert sent_requests[0].method == "GET"
    assert (
        sent_requests[0].url
        == "https://api.razorpay.com/v1/payments/pay_test/refunds/rfnd_test"
    )
    assert "private" not in caplog.text
    assert "test-key-secret" not in caplog.text


def test_create_full_refund_without_credentials_fails_before_request(monkeypatch):
    client = MagicMock()
    service = RazorpayService(client=client)
    service._api_credentials_configured = False

    with pytest.raises(RazorpayRefundNotSubmittedError):
        service.create_full_refund("pay_test", 2510, "refund-key-123")

    client.payment.refund.assert_not_called()


def test_refund_lookup_methods_use_payment_scoped_sdk_apis():
    client = MagicMock()
    refund = {"id": "rfnd_test", "payment_id": "pay_test"}
    refunds = {"items": [refund]}
    client.payment.fetch_refund_id.return_value = refund
    client.payment.fetch_multiple_refund.return_value = refunds
    service = RazorpayService(client=client)

    assert service.fetch_refund("pay_test", "rfnd_test") == refund
    assert service.fetch_payment_refunds("pay_test") == refunds
    client.payment.fetch_refund_id.assert_called_once()
    assert client.payment.fetch_refund_id.call_args.args == (
        "pay_test",
        "rfnd_test",
    )
    assert (
        len(client.payment.fetch_refund_id.call_args.kwargs["hooks"]["response"]) == 1
    )
    client.payment.fetch_multiple_refund.assert_called_once()
    assert client.payment.fetch_multiple_refund.call_args.args == ("pay_test",)
    assert len(
        client.payment.fetch_multiple_refund.call_args.kwargs["hooks"]["response"]
    ) == 1


def test_fetch_payment_refunds_returns_sdk_decoded_collection(monkeypatch, caplog):
    collection = {
        "entity": "collection",
        "count": 1,
        "items": [
            {
                "id": "rfnd_test",
                "payment_id": "pay_test",
                "amount": 2510,
                "currency": "INR",
                "status": "processed",
            }
        ],
    }
    client, sent_requests = _sdk_client_with_response(
        monkeypatch, 200, json.dumps(collection).encode(), "application/json"
    )
    service = RazorpayService(client=client)

    result = service.fetch_payment_refunds("pay_test")

    assert isinstance(result, dict)
    assert result == collection
    assert len(sent_requests) == 1
    assert sent_requests[0].method == "GET"
    assert (
        sent_requests[0].url
        == "https://api.razorpay.com/v1/payments/pay_test/refunds"
    )
    assert "test-key-secret" not in caplog.text


def test_fetch_payment_refunds_reports_sanitized_lookup_failure(
    monkeypatch, caplog
):
    client, sent_requests = _sdk_client_with_response(
        monkeypatch,
        503,
        b'{"error":{"description":"private provider details"}}',
        "application/json",
    )
    service = RazorpayService(client=client)

    with pytest.raises(RazorpayLookupError) as error:
        service.fetch_payment_refunds("pay_test")

    assert error.value.failure_classification == "provider_server_error"
    assert error.value.provider_http_status == 503
    assert len(sent_requests) == 1
    assert "private provider details" not in str(error.value)
    assert "private provider details" not in caplog.text
    assert "test-key-secret" not in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        BadRequestError("private provider details"),
        ServerError("private provider details"),
        requests.exceptions.Timeout("private provider details"),
    ],
)
def test_refund_lookup_failures_are_translated(failure):
    client = MagicMock()
    client.payment.fetch_refund_id.side_effect = failure
    service = RazorpayService(client=client)

    with pytest.raises(RazorpayIntegrationError) as error:
        service.fetch_refund("pay_test", "rfnd_test")

    assert "private provider details" not in str(error.value)
    if isinstance(failure, BadRequestError):
        assert "rejected the refund lookup" in str(error.value)
    elif isinstance(failure, ServerError):
        assert "server error for the refund lookup" in str(error.value)
    else:
        assert "could not reach the provider" in str(error.value)
    assert "private provider details" not in str(error.value)


def test_create_full_refund_marks_provider_rejection_as_definitive(caplog):
    client = MagicMock()
    client.payment.refund.side_effect = BadRequestError("private provider details")
    service = RazorpayService(client=client)

    with pytest.raises(RazorpayRefundRejectedError) as error:
        service.create_full_refund("pay_test", 2510, "refund-key-123")

    assert str(error.value) == "Razorpay refund request was rejected"
    assert "private provider details" not in str(error.value)
    failure_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "request_failed"
    )
    assert failure_log.failure_classification == "definitive_rejection"
    assert failure_log.provider_refund_id_returned is False


@pytest.mark.parametrize(
    ("failure", "expected_classification"),
    [
        (GatewayError("private provider details"), "gateway_error"),
        (ServerError("private provider details"), "server_error"),
        (requests.exceptions.Timeout("private provider details"), "timeout"),
        (
            requests.exceptions.ConnectionError("private provider details"),
            "transport_error",
        ),
    ],
)
def test_create_full_refund_marks_transport_failures_as_uncertain(
    failure, expected_classification, caplog
):
    client = MagicMock()
    client.payment.refund.side_effect = failure
    service = RazorpayService(client=client)

    with pytest.raises(RazorpayRefundOutcomeUnknownError) as error:
        service.create_full_refund("pay_test", 2510, "refund-key-123")

    assert str(error.value) == "Razorpay refund outcome is unknown"
    assert "private provider details" not in str(error.value)
    assert error.value.failure_classification == expected_classification
    failure_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "request_failed"
    )
    assert failure_log.failure_classification == expected_classification
    assert failure_log.provider_refund_id_returned is False
    assert "private provider details" not in str(failure_log.__dict__)


@pytest.mark.parametrize(
    "payment_response",
    [
        {
            "order_id": "different_order",
            "status": "captured",
            "amount": 2510,
            "currency": "INR",
        },
        {
            "order_id": "order_test",
            "status": "authorized",
            "amount": 2510,
            "currency": "INR",
        },
        {
            "order_id": "order_test",
            "status": "captured",
            "amount": 2500,
            "currency": "INR",
        },
        {
            "order_id": "order_test",
            "status": "captured",
            "amount": 2510,
            "currency": "USD",
        },
    ],
)
def test_verify_payment_rejects_non_captured_or_mismatched_payment(payment_response):
    client = MagicMock()
    client.utility.verify_payment_signature.return_value = True
    client.payment.fetch.return_value = payment_response
    service = RazorpayService(client=client)

    assert not service.verify_payment(
        "order_test",
        "pay_test",
        "signature_test",
        expected_amount=2510,
        expected_currency="INR",
    )


@pytest.mark.parametrize(
    "payment_changes",
    [
        {"amount": 2500},
        {"currency": "USD"},
        {"amount": True},
        {"amount": 2510.0},
        {"amount": "2510"},
        {"amount": None},
    ],
)
def test_verify_payment_rejects_amount_or_currency_mismatch(payment_changes):
    client = MagicMock()
    client.utility.verify_payment_signature.return_value = True
    client.payment.fetch.return_value = {
        "order_id": "order_test",
        "status": "captured",
        "amount": 2510,
        "currency": "INR",
        **payment_changes,
    }
    service = RazorpayService(client=client)

    assert not service.verify_payment(
        "order_test",
        "pay_test",
        "signature_test",
        expected_amount=2510,
        expected_currency="INR",
    )


def test_webhook_signature_uses_raw_body_and_separate_webhook_secret(monkeypatch):
    client = MagicMock()
    client.utility.verify_webhook_signature.return_value = True
    monkeypatch.setattr(
        "app.services.razorpay.settings.razorpay_webhook_secret",
        SecretStr("test_webhook_secret"),
    )
    service = RazorpayService(client=client)
    raw_body = b'{ "event":"payment.captured", "payload":{} }'

    assert service.verify_webhook_signature(raw_body, "test_signature")
    client.utility.verify_webhook_signature.assert_called_once_with(
        raw_body.decode("utf-8"), "test_signature", "test_webhook_secret"
    )


def test_invalid_webhook_signature_is_safely_rejected(monkeypatch):
    client = MagicMock()
    client.utility.verify_webhook_signature.side_effect = SignatureVerificationError(
        "test_webhook_secret"
    )
    monkeypatch.setattr(
        "app.services.razorpay.settings.razorpay_webhook_secret",
        SecretStr("test_webhook_secret"),
    )
    service = RazorpayService(client=client)

    assert not service.verify_webhook_signature(b"{}", "invalid")


def test_webhook_secret_loads_separately_from_api_secret(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test_api_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret")

    configured = Settings(
        _env_file=None,
        database_url="postgresql://localhost/test",
    )

    assert configured.razorpay_key_secret == SecretStr("test_api_secret")
    assert configured.razorpay_webhook_secret == SecretStr("test_webhook_secret")
    assert configured.razorpay_key_secret != configured.razorpay_webhook_secret
    assert "test_webhook_secret" not in repr(configured)


@pytest.mark.parametrize(
    "failure",
    [
        ServerError("test-secret"),
        requests.exceptions.ConnectionError("test-secret"),
    ],
)
def test_create_order_sanitizes_client_failures(failure):
    client = MagicMock()
    client.order.create.side_effect = failure
    service = RazorpayService(client=client)

    with pytest.raises(RazorpayIntegrationError) as error:
        service.create_order(amount=50000, receipt="booking-receipt")

    assert str(error.value) == "Razorpay order creation failed"
    assert "test-secret" not in str(error.value)
    assert error.value.__cause__ is None


def test_razorpay_credentials_load_from_environment(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "test_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test_key_secret")

    configured = Settings(
        _env_file=None,
        database_url="postgresql://user:password@localhost/test",
    )

    assert configured.razorpay_key_id == "test_key_id"
    assert configured.razorpay_key_secret == SecretStr("test_key_secret")
    assert "test_key_secret" not in repr(configured)
