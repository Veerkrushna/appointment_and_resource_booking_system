from typing import Annotated

from fastapi import APIRouter, Depends, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    CustomerLogin,
    CustomerProfileUpdate,
    CustomerRegister,
    CustomerResponse,
)
from app.services.auth_service import (
    register_user,
    authenticate_user,
    update_user_profile,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(user.id, user.role),
        user=CustomerResponse.model_validate(user),
    )


@router.post(
    "/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def register_customer(
    payload: CustomerRegister,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
):
    user = register_user(db, payload, background_tasks)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login_customer(payload: CustomerLogin, db: Annotated[Session, Depends(get_db)]):
    user = authenticate_user(db, payload.email, payload.password)
    return _auth_response(user)


@router.get("/me", response_model=CustomerResponse)
def current_user(user: Annotated[User, Depends(get_current_user)]):
    return user


@router.patch("/me", response_model=CustomerResponse)
def update_current_user(
    payload: CustomerProfileUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    updated_user = update_user_profile(db, user, payload)
    return updated_user
