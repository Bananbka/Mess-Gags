import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.domains.chats.models import ParticipantRole, ChatType


class PrivateChatCreateRequest(BaseModel):
    target_user_id: uuid.UUID


class GroupChatCreateRequest(BaseModel):
    title: str
    description: str | None = None
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
    created_at: datetime

    participants: list[ChatParticipantResponse] = []

    model_config = ConfigDict(from_attributes=True)
