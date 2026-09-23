from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import hash_password, verify_password
from app.db.database import SessionLocal
from app.main import app
from app.models.password_reset_otp import PasswordResetOtp
from app.models.user import User, UserRole

client = TestClient(app)


@pytest.fixture
def reset_user():
    db = SessionLocal()
    user = User(
        id=uuid4(),
        name="Reset Test User",
        email=f"reset-test-{uuid4()}@example.com",
        password_hash=hash_password("oldpassword"),
        phone="555-0000",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    yield user

    cleanup = SessionLocal()
    cleanup.execute(delete(PasswordResetOtp).where(PasswordResetOtp.user_id == user.id))
    cleanup.execute(delete(User).where(User.id == user.id))
    cleanup.commit()
    cleanup.close()
    db.close()


def test_password_reset_request(reset_user):
    with patch("app.api.routes.password_reset.send_email") as mock_send:
        response = client.post(
            "/api/password-reset/request", json={"email": reset_user.email}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "If this email exists, a code has been sent"}
        mock_send.assert_called_once()

        db = SessionLocal()
        otp = db.query(PasswordResetOtp).filter_by(user_id=reset_user.id).first()
        assert otp is not None
        assert otp.used is False
        db.close()


def test_password_reset_verify_and_confirm(reset_user, monkeypatch):
    import secrets
    monkeypatch.setattr(secrets, "randbelow", lambda _: 123456)

    with patch("app.api.routes.password_reset.send_email"):
        client.post(
            "/api/password-reset/request", json={"email": reset_user.email}
        )

    verify_response = client.post(
        "/api/password-reset/verify",
        json={"email": reset_user.email, "pin": "123456"},
    )
    assert verify_response.status_code == 200
    token = verify_response.json()["reset_token"]

    with patch("app.api.routes.password_reset.send_email") as mock_confirm:
        confirm_response = client.post(
            "/api/password-reset/confirm",
            json={"reset_token": token, "new_password": "newStrongPassword1!"},
        )
        assert confirm_response.status_code == 200
        mock_confirm.assert_called_once()

    db = SessionLocal()
    updated_user = db.get(User, reset_user.id)
    assert verify_password("newStrongPassword1!", updated_user.password_hash)
    db.close()


def test_password_reset_expired_pin(reset_user):
    db = SessionLocal()
    otp = PasswordResetOtp(
        user_id=reset_user.id,
        pin_hash=hash_password("111111"),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db.add(otp)
    db.commit()
    db.close()

    verify_response = client.post(
        "/api/password-reset/verify",
        json={"email": reset_user.email, "pin": "111111"},
    )
    assert verify_response.status_code == 400
    assert verify_response.json()["detail"] == "Invalid or expired code"


def test_password_reset_too_many_attempts(reset_user):
    db = SessionLocal()
    otp = PasswordResetOtp(
        user_id=reset_user.id,
        pin_hash=hash_password("222222"),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        attempts=5,
    )
    db.add(otp)
    db.commit()
    otp_id = otp.id
    db.close()

    verify_response = client.post(
        "/api/password-reset/verify",
        json={"email": reset_user.email, "pin": "222222"},
    )
    assert verify_response.status_code == 429
    assert verify_response.json()["detail"] == "Too many attempts, request a new code."

    # Try again, verify it still fails and is marked used
    db = SessionLocal()
    updated_otp = db.get(PasswordResetOtp, otp_id)
    assert updated_otp.used is True
    db.close()
