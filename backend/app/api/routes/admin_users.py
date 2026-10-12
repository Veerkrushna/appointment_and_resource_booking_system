from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, require_role
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import AdminUserCreate, CustomerResponse

router = APIRouter(prefix="/api/admin/users", tags=["Admin Users"])


@router.get("", response_model=list[CustomerResponse])
def list_admin_users(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    role: UserRole | None = None,
):
    query = select(User)
    if role is not None:
        query = query.where(User.role == role)
    # Admin cannot see his own name/account in list
    query = query.where(User.id != admin.id).order_by(User.created_at.desc())
    return db.scalars(query).all()


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_admin_user(
    payload: AdminUserCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
):
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
        role=payload.role,
        created_by=admin.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/status", response_model=CustomerResponse)
def update_admin_user_status(
    user_id: UUID,
    is_active: bool,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify your own status",
        )
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user

