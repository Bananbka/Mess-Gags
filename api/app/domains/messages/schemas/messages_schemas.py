import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class MessageCreateRequest(BaseModel):
    chat_id: uuid.UUID
    encrypted_content: str
    reply_to_message_id: str | None = None


class MessageDocument(BaseModel):
    chat_id: uuid.UUID
    sender_id: uuid.UUID
    encrypted_content: str
    reply_to_message_id: str | None = None

    is_read: bool = False
    is_pinned: bool = False

    created_at: datetime.datetime


class MessageResponse(BaseModel):
    id: str = Field(alias="_id")
    chat_id: uuid.UUID
    sender_id: uuid.UUID
    encrypted_content: str
    reply_to_message_id: uuid.UUID | None
    created_at: datetime.datetime

    is_read: bool = False
    is_pinned: bool = False

    model_config = ConfigDict(from_attributes=True)
