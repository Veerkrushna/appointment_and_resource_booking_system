from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, require_role
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import AdminUserCreate, CustomerResponse

router = APIRouter(prefix="/api/admin/users", tags=["Admin Users"])


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_admin_user(
    payload: AdminUserCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    user = User(
        name=payload.name.strip(),
        email=email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=payload.role,
        created_by=admin.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
