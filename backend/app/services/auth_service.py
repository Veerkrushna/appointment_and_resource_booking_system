import os
from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import CustomerProfileUpdate, CustomerRegister
from app.services.notifications import send_email


def register_user(
    db: Session, payload: CustomerRegister, background_tasks: BackgroundTasks
) -> User:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user = User(
        name=payload.name.strip(),
        email=email,
        phone=payload.phone,
        photo=payload.photo,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    subject = f"Welcome to {settings.app_name}!"
    body = (
        f"Dear {user.name},\n"
        f"Welcome to {settings.app_name}.\n"
        "Your account has been created Successfully !\n"
        "Avoid last moment rush by booking Appointments at anytime from anywhere !"
    )
    background_tasks.add_task(send_email, user.email, subject, body)

    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return user


def update_user_profile(db: Session, user: User, payload: CustomerProfileUpdate) -> User:
    email = payload.email.lower()

    existing_user = db.scalar(
        select(User).where(
            User.email == email,
            User.id != user.id,
        )
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user.name = payload.name.strip()
    user.email = email
    user.phone = payload.phone

    if user.photo and payload.photo and user.photo != payload.photo:
        if user.photo.startswith("/uploads/"):
            old_file_path = user.photo.lstrip("/")
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except Exception:
                    pass

    user.photo = payload.photo

    db.commit()
    db.refresh(user)

    return user
