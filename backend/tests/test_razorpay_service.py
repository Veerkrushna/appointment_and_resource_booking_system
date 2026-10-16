from unittest.mock import MagicMock

import pytest
import requests
from pydantic import SecretStr
from razorpay.errors import BadRequestError, ServerError, SignatureVerificationError

from app.core.config import Settings
from app.services.razorpay import (
    RazorpayIntegrationError,
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
    client.payment.fetch.assert_called_once_with("pay_test")


def test_create_full_refund_uses_sdk_payment_refund_api():
    client = MagicMock()
    refund = {"id": "rfnd_test"}
    client.payment.refund.return_value = refund
    service = RazorpayService(client=client)

    assert service.create_full_refund("pay_test", 2510, "refund-key-123") == refund
    client.payment.refund.assert_called_once_with(
        "pay_test",
        2510,
        headers={"X-Refund-Idempotency": "refund-key-123"},
    )


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
    client.payment.fetch_refund_id.assert_called_once_with("pay_test", "rfnd_test")
    client.payment.fetch_multiple_refund.assert_called_once_with("pay_test")


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

    assert str(error.value) == "Razorpay refund lookup failed"
    assert "private provider details" not in str(error.value)


def test_create_full_refund_marks_provider_rejection_as_definitive():
    client = MagicMock()
    client.payment.refund.side_effect = BadRequestError("private provider details")
    service = RazorpayService(client=client)

    with pytest.raises(RazorpayRefundRejectedError) as error:
        service.create_full_refund("pay_test", 2510, "refund-key-123")

    assert str(error.value) == "Razorpay refund request was rejected"
    assert "private provider details" not in str(error.value)


@pytest.mark.parametrize(
    "failure",
    [
        ServerError("private provider details"),
        requests.exceptions.Timeout("private provider details"),
        requests.exceptions.ConnectionError("private provider details"),
    ],
)
def test_create_full_refund_marks_transport_failures_as_uncertain(failure):
    client = MagicMock()
    client.payment.refund.side_effect = failure
    service = RazorpayService(client=client)

    with pytest.raises(RazorpayRefundOutcomeUnknownError) as error:
        service.create_full_refund("pay_test", 2510, "refund-key-123")

    assert str(error.value) == "Razorpay refund outcome is unknown"
    assert "private provider details" not in str(error.value)


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
