from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Credentials(InputModel):
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class Registration(Credentials):
    full_name: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=15, max_length=128)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("A valid display name is required")
        return value


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    full_name: str
    role: Literal["student", "contributor", "admin"]
    is_active: bool
    created_at: datetime


class TokenView(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    csrf_token: str
    user: UserView


class PasswordChange(InputModel):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=15, max_length=128)


class UserUpdate(InputModel):
    role: Literal["student", "contributor"] | None = None
    is_active: bool | None = None


class UserPage(BaseModel):
    items: list[UserView]
    total: int
    offset: int
    limit: int
