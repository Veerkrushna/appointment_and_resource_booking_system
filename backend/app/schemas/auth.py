from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class CustomerRegister(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=30)

    model_config = ConfigDict(extra="ignore")


class CustomerLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    phone: str | None
    role: UserRole
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CustomerResponse

    @property
    def customer(self) -> CustomerResponse:
        return self.user


class AdminUserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    phone: str | None = Field(default=None, max_length=30)

    def model_post_init(self, __context: object) -> None:
        if self.role not in {UserRole.ADMIN, UserRole.SERVICE_PROVIDER}:
            raise ValueError("Admin users can only create admin or service_provider accounts")
