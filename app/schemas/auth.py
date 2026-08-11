from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.auth import normalize_username

Role = Literal["ADMIN", "OPERATOR", "VIEWER"]
AccountStatus = Literal["PENDING", "ACTIVE", "LOCKED", "DISABLED"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalized_username(cls, value: str) -> str:
        return normalize_username(value)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    role: Role = "OPERATOR"
    temporary_password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalized_username(cls, value: str) -> str:
        return normalize_username(value)


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    role: Role | None = None
    status: AccountStatus | None = None


class AdminResetPasswordRequest(BaseModel):
    temporary_password: str = Field(min_length=12, max_length=128)
