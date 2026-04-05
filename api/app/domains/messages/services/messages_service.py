import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.domains.chats.models import ChatParticipant
from app.domains.messages.schemas.messages_schemas import MessageCreateRequest, MessageDocument, MessageResponse
from app.domains.users.models import User


async def is_user_in_chat(
        db: AsyncSession,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
) -> User | None:
    stmt = select(ChatParticipant).where(ChatParticipant.user_id == user_id, ChatParticipant.chat_id == chat_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


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

    chat_id = msg.get("chat_id")
    prt = await is_user_in_chat(db, user_id, chat_id)
    if not prt:
        raise AppException(403, "FORBIDDEN", "You are not participant of this chat.")

    return msg


async def send_message(
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        message_in: MessageCreateRequest
) -> MessageResponse:
    prt = await is_user_in_chat(db, user_id, message_in.chat_id)
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


async def get_chat_massages(
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0
) -> list[MessageResponse]:
    prt = await is_user_in_chat(db, user_id, chat_id)
    if not prt:
        raise AppException(403, "FORBIDDEN", "You are not participant of this chat.")

    collection = mongo_db["messages"]
    crs = (
        collection
        .find({"chat_id": chat_id})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    messages = await crs.to_list(length=limit)

    res = []
    for msg in messages:
        msg["_id"] = str(msg["_id"])
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

    await collection.update_one(
        {"_id": obj_id},
        {"$set": {"encrypted_content": encrypted_content, "is_edited": True}}
    )

    upd_msg = await collection.find_one({"_id": obj_id})
    upd_msg["_id"] = str(obj_id)
    return MessageResponse(**upd_msg)


async def delete_message(
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        msg_id: str,
) -> bool:
    collection = mongo_db["messages"]
    msg = await get_and_validate_message(db, collection, msg_id, user_id)

    res = await collection.delete_one({"_id": msg["_id"]})
    return res.deleted_count > 0
