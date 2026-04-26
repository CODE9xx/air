"""Pydantic-схемы auth endpoints."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    locale: str = Field(default="ru", pattern=r"^(ru|en)$")
    phone: str | None = Field(default=None, max_length=32)


class RegisterResponse(BaseModel):
    user_id: str
    workspace_id: str
    email_verification_required: bool = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserBrief(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    locale: str = "ru"
    email_verified: bool = False


class LoginResponse(BaseModel):
    access_token: str
    access_token_expires_in: int
    user: UserBrief


class RefreshResponse(BaseModel):
    access_token: str
    access_token_expires_in: int


class VerifyEmailConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class VerifyEmailWithEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class VerifyEmailResendRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChangeRequest(BaseModel):
    """Смена пароля — принимает ``old_password`` или ``current_password`` (бриф)."""

    old_password: str = Field(
        min_length=1,
        max_length=128,
        validation_alias=AliasChoices("current_password", "old_password"),
    )
    new_password: str = Field(min_length=8, max_length=128)

    model_config = {"populate_by_name": True}


class EmailChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_email: EmailStr


class EmailChangeConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    locale: str = "ru"
    email_verified: bool = False
    two_factor_enabled: bool = False
    workspaces: list[dict] = Field(default_factory=list)
