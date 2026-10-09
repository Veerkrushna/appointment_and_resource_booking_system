from unittest.mock import MagicMock

import pytest
import requests
from pydantic import SecretStr
from razorpay.errors import ServerError, SignatureVerificationError

from app.core.config import Settings
from app.services.razorpay import RazorpayIntegrationError, RazorpayService


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
    }
    service = RazorpayService(client=client)

    assert service.verify_payment("order_test", "pay_test", "signature_test")
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

    assert not service.verify_payment("order_test", "pay_test", "invalid")
    client.payment.fetch.assert_not_called()


@pytest.mark.parametrize(
    "payment_response",
    [
        {"order_id": "different_order", "status": "captured"},
        {"order_id": "order_test", "status": "authorized"},
    ],
)
def test_verify_payment_rejects_non_captured_or_mismatched_payment(payment_response):
    client = MagicMock()
    client.utility.verify_payment_signature.return_value = True
    client.payment.fetch.return_value = payment_response
    service = RazorpayService(client=client)

    assert not service.verify_payment("order_test", "pay_test", "signature_test")


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
