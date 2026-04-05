import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.domains.chats.models import ChatParticipant
from app.domains.messages.schemas.messages_schemas import MessageCreateRequest, MessageDocument, MessageResponse


async def send_message(
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        message_in: MessageCreateRequest
) -> MessageResponse:
    stmt = select(ChatParticipant).where(
        ChatParticipant.user_id == user_id,
        ChatParticipant.chat_id == message_in.chat_id
    )

    res = await db.execute(stmt)
    prt = res.scalar_one_or_none()

    if not prt:
        raise AppException(403, "FORBIDDEN", "You are not participant of this chat.")

    new_message = MessageDocument(
        chat_id=message_in.chat_id,
        sender_id=user_id,
        encrypted_content=message_in.encrypted_content,
        reply_to_message_id=message_in.reply_to_message_id,
        created_at=datetime.now(timezone.utc)
    )

    message_dict = new_message.model_dump()

    collection = mongo_db["messages"]
    res = await collection.insert_one(message_dict)

    message_dict["_id"] = str(res.inserted_id)

    return MessageResponse(**message_dict)
