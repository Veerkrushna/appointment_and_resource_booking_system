import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    create_reset_token,
    hash_password,
    verify_password,
    verify_reset_token,
)
from app.db.database import get_db
from app.models.password_reset_otp import PasswordResetOtp
from app.models.user import User
from app.schemas.auth import (
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetVerify,
    PasswordResetVerifyResponse,
)
from app.services.notifications import send_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/password-reset", tags=["Password Reset"])


@router.post("/request", status_code=status.HTTP_200_OK)
def request_password_reset(
    payload: PasswordResetRequest, background_tasks: BackgroundTasks, db: Annotated[Session, Depends(get_db)]
):
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))

    if not user:
        subject = "Password Reset Request"
        body = (
            "Someone requested a password reset for this email address, "
            "but no account is associated with it in our system.\n\n"
            "If you did not request this, you can safely ignore this email."
        )
        try:
            background_tasks.add_task(send_email, email, subject, body)
        except Exception:
            logger.exception("Failed to queue 'no account' email")
        return {"message": "If this email exists, a code has been sent"}

    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)

    # Rate limiting: max 3 requests per email per hour
    recent_requests = db.scalar(
        select(PasswordResetOtp)
        .where(PasswordResetOtp.user_id == user.id, PasswordResetOtp.created_at >= one_hour_ago)
        .with_only_columns(PasswordResetOtp.id)
        .correlate(PasswordResetOtp)
    )  # We just need count, but a query with count() is better
    
    # Actually let's just count
    recent_count = db.query(PasswordResetOtp).filter(
        PasswordResetOtp.user_id == user.id,
        PasswordResetOtp.created_at >= one_hour_ago
    ).count()

    if recent_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    # Generate 6-digit PIN
    pin = f"{secrets.randbelow(1000000):06d}"

    # Invalidate existing unused OTPs
    db.query(PasswordResetOtp).filter(
        PasswordResetOtp.user_id == user.id,
        PasswordResetOtp.used == False
    ).update({"used": True})

    # Save new OTP
    otp = PasswordResetOtp(
        user_id=user.id,
        pin_hash=hash_password(pin),
        expires_at=now + timedelta(minutes=5),  # 5 minute expiry as per comment
    )
    db.add(otp)
    db.commit()

    # Send email
    subject = "Password Reset Code"
    body = (
        f"Your password reset code is: {pin}\n\n"
        "This code will expire in 5 minutes.\n"
        "If you didn't request this, you can safely ignore this email."
    )
    try:
        background_tasks.add_task(send_email, user.email, subject, body)
    except Exception:
        logger.exception("Failed to queue password reset email")

    return {"message": "If this email exists, a code has been sent"}


@router.post("/verify", response_model=PasswordResetVerifyResponse)
def verify_password_reset(
    payload: PasswordResetVerify, db: Annotated[Session, Depends(get_db)]
):
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))

    # We shouldn't leak user existence easily, but OTP must match.
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    now = datetime.now(UTC)

    # Fetch latest unused, non-expired OTP
    otp = db.scalar(
        select(PasswordResetOtp)
        .where(
            PasswordResetOtp.user_id == user.id,
            PasswordResetOtp.used == False,
            PasswordResetOtp.expires_at > now
        )
        .order_by(PasswordResetOtp.created_at.desc())
        .limit(1)
    )

    if not otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    if otp.attempts >= 5:
        # Mark as used to prevent further attempts on this token
        otp.used = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts, request a new code.",
        )

    if not verify_password(payload.pin, otp.pin_hash):
        otp.attempts += 1
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    # Success
    otp.used = True
    db.commit()

    reset_token = create_reset_token(user.id)
    return {"reset_token": reset_token}


@router.post("/confirm")
def confirm_password_reset(
    payload: PasswordResetConfirm, background_tasks: BackgroundTasks, db: Annotated[Session, Depends(get_db)]
):
    try:
        user_id = verify_reset_token(payload.reset_token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired reset token",
        )

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    # Send confirmation email
    subject = "Your password was just changed"
    body = (
        f"Hello {user.name},\n\n"
        "Your password was successfully changed. If you did not perform this action, "
        "please contact support immediately."
    )
    try:
        background_tasks.add_task(send_email, user.email, subject, body)
    except Exception:
        logger.exception("Failed to queue password reset confirmation email")

    return {"message": "Password updated successfully"}
