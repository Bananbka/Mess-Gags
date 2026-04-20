import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class MessageDocument(BaseModel):
    chat_id: uuid.UUID
    sender_id: uuid.UUID
    encrypted_content: str
    reply_to_message_id: str | None = None

    attachments: list[dict] | None = None

    is_read: bool = False
    is_pinned: bool = False
    is_edited: bool = False

    created_at: datetime.datetime


class MessageResponse(BaseModel):
    id: str = Field(alias="_id")
    chat_id: uuid.UUID
    sender_id: uuid.UUID
    encrypted_content: str
    reply_to_message_id: str | None
    created_at: datetime.datetime

    attachments: list[dict] | None = None

    is_read: bool = False
    is_pinned: bool = False
    is_edited: bool = False
    is_encrypted: bool = True

    model_config = ConfigDict(from_attributes=True)


class MessageCreateRequest(BaseModel):
    chat_id: uuid.UUID
    encrypted_content: str
    reply_to_message_id: str | None = None

    attachments: list[dict] | None = None


class MessageUpdateRequest(BaseModel):
    encrypted_content: str
