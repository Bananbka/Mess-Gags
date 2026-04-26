import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domains.chats.models import ParticipantRole, ChatType


class PrivateChatCreateRequest(BaseModel):
    target_user_id: uuid.UUID


class GroupChatCreateRequest(BaseModel):
    title: str
    description: str
    avatar_url: str | None = None
    participant_ids: list[uuid.UUID] = []


class ChatParticipantResponse(BaseModel):
    user_id: uuid.UUID
    role: ParticipantRole
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatResponse(BaseModel):
    id: uuid.UUID
    chat_type: ChatType

    title: str | None = None
    avatar_url: str | None = None

    unread_count: int = 0
    last_message: Any = None

    created_at: datetime
    updated_at: datetime | None = None

    participants: list[ChatParticipantResponse] = []

    model_config = ConfigDict(from_attributes=True)


class UserListRequest(BaseModel):
    user_ids: list[uuid.UUID]
