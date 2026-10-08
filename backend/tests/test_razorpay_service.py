from unittest.mock import MagicMock

import pytest
import requests
from pydantic import SecretStr
from razorpay.errors import ServerError

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
