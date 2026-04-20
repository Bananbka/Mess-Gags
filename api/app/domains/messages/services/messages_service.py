import asyncio
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.domains.chats.models import ChatParticipant, Chat, ChatType
from app.domains.messages.schemas.messages_schemas import MessageCreateRequest, MessageDocument, MessageResponse
from app.infrastructure.minio import minio_manager


async def is_user_in_chat(
        db: AsyncSession,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
) -> ChatParticipant | None:
    stmt = select(ChatParticipant).where(ChatParticipant.user_id == user_id, ChatParticipant.chat_id == chat_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def is_user_in_all_chats(
        db: AsyncSession,
        user_id: uuid.UUID,
        chat_ids: list[uuid.UUID]
):
    stmt = select(func.count()).select_from(ChatParticipant).where(ChatParticipant.user_id == user_id,
                                                                   ChatParticipant.chat_id.in_(chat_ids))

    res = await db.execute(stmt)
    cp = res.scalar_one()

    return cp == len(chat_ids)


async def get_chat_or_403(db: AsyncSession, chat_id: uuid.UUID, user_id: uuid.UUID) -> Chat:
    stmt = (
        select(ChatParticipant, Chat)
        .join(Chat, Chat.id == ChatParticipant.chat_id)
        .where(
            ChatParticipant.user_id == user_id,
            ChatParticipant.chat_id == chat_id
        )
    )
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise AppException(403, "FORBIDDEN", "You are not a participant of this chat.")

    _, chat = row.ChatParticipant, row.Chat
    return chat


def objectify_id(id_: str) -> ObjectId:
    try:
        return ObjectId(id_)
    except InvalidId:
        raise AppException(400, "INVALID_ID", "Message id is invalid.")


async def get_message_by_id(collection, id_: ObjectId) -> dict:
    msg = await collection.find_one({"_id": id_})
    if not msg:
        raise AppException(404, "NOT_FOUND", "Message not found.")
    return msg


async def get_and_validate_message(db: AsyncSession, collection, msg_id: str, user_id: uuid.UUID):
    obj_id = objectify_id(msg_id)

    msg = await get_message_by_id(collection, obj_id)

    if msg.get("sender_id") != user_id:
        raise AppException(403, "FORBIDDEN", "You are not sender of this message.")

    return msg


async def send_message(
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        message_in: MessageCreateRequest
) -> MessageResponse:
    chat = await get_chat_or_403(db, message_in.chat_id, user_id)

    message_dict = {
        "created_at": datetime.now(timezone.utc),
        "sender_id": user_id,
        "is_encrypted": chat.chat_type == ChatType.PRIVATE,
        **message_in.model_dump(),
    }
    new_message = MessageDocument(**message_dict)

    message_dict = new_message.model_dump()

    collection = mongo_db["messages"]
    res = await collection.insert_one(message_dict)

    message_dict["_id"] = str(res.inserted_id)

    return MessageResponse(**message_dict)


async def get_chat_messages(
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
        limit: int = 50,
        before_id: str | None = None
) -> list[MessageResponse]:
    chat = await get_chat_or_403(db, chat_id, user_id)

    collection = mongo_db["messages"]
    query = {"chat_id": chat_id}

    if before_id:
        message_id = objectify_id(before_id)
        query["_id"] = {"$lt": message_id}

    crs = (
        collection
        .find(query)
        .sort("_id", -1)
        .limit(limit)
    )
    messages = await crs.to_list(length=limit)

    res = []
    for msg in messages:
        msg["_id"] = str(msg["_id"])
        msg["is_encrypted"] = chat.chat_type == ChatType.PRIVATE
        res.append(MessageResponse(**msg))

    return res


async def update_message(
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        msg_id: str,
        encrypted_content: str
) -> MessageResponse:
    collection = mongo_db["messages"]

    msg = await get_and_validate_message(db, collection, msg_id, user_id)
    obj_id = msg["_id"]

    chat_id = msg.get("chat_id")
    chat = await get_chat_or_403(db, chat_id, user_id)

    await collection.update_one(
        {"_id": obj_id},
        {"$set": {"encrypted_content": encrypted_content, "is_edited": True}}
    )

    upd_msg = await collection.find_one({"_id": obj_id})
    upd_msg["_id"] = str(obj_id)
    upd_msg["is_encrypted"] = chat.chat_type == ChatType.PRIVATE
    return MessageResponse(
        **upd_msg
    )


async def delete_message(
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        msg_id: str,
) -> uuid.UUID:
    collection = mongo_db["messages"]
    msg = await get_and_validate_message(db, collection, msg_id, user_id)

    attachments = msg.get("attachments", [])
    for attachment in attachments:
        file_url = attachment.get("url")
        if file_url:
            asyncio.create_task(minio_manager.delete_file(file_url, settings.MINIO_MESSAGE_BUCKET))

    await collection.delete_one({"_id": msg["_id"]})
    return msg["chat_id"]


async def mark_messages_as_read(
        mongo_db: AsyncIOMotorDatabase,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
        last_read_message_id: str
) -> int:
    collection = mongo_db["messages"]

    message_id = objectify_id(last_read_message_id)

    result = await collection.update_many(
        {
            "chat_id": chat_id,
            "sender_id": {"$ne": user_id},
            "is_read": False,
            "_id": {"$lte": message_id}
        },
        {"$set": {"is_read": True}}
    )

    return result.modified_count
