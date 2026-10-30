from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.crypto import now, utc
from app.schemas.identity import InputModel


class ConversationCreate(InputModel):
    client_id: UUID


class ConversationUpdate(InputModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("A nonempty title without control characters is required")
        return value.strip()


class TurnCreate(InputModel):
    request_id: UUID
    content: str = Field(min_length=1, max_length=4000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=2)

    @field_validator("attachment_ids")
    @classmethod
    def unique_attachments(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Attachments must be unique")
        return value

    @field_validator("content")
    @classmethod
    def clean_question(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 and c not in "\n\t\r" for c in value):
            raise ValueError("A question without invalid control characters is required")
        return value.strip()


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    attachments: list[dict] = Field(default_factory=list)
    provider: str | None
    created_at: datetime


class RequestView(BaseModel):
    id: UUID
    status: Literal["pending", "succeeded", "failed"]
    error_code: str | None
    deadline_at: datetime

    @classmethod
    def from_record(cls, record):
        expired = record.status == "pending" and utc(record.deadline_at) <= now()
        return cls(
            id=record.id,
            status="failed" if expired else record.status,
            error_code="interrupted" if expired else record.error_code,
            deadline_at=record.deadline_at,
        )


class ConversationPage(BaseModel):
    items: list[ConversationView]
    total: int
    offset: int
    limit: int


class ConversationDetail(BaseModel):
    conversation: ConversationView
    messages: list[MessageView]
    requests: list[RequestView]
    has_older: bool


class TurnResult(BaseModel):
    request: RequestView
    messages: list[MessageView]
    replayed: bool
