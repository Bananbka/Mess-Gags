import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select, func, Integer, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.domains.chats.models import Chat, ChatParticipant, ChatType, ParticipantRole
from app.domains.messages.services.messages_service import objectify_id
from app.domains.users.services.user_service import get_user_by_id


async def get_or_create_private_chat(
        db: AsyncSession,
        current_user_id: uuid.UUID,
        target_user_id: uuid.UUID
) -> Chat:
    if current_user_id == target_user_id:
        raise AppException(400, "INVALID_TARGET", "You cannot create chat with yourself")

    target_user = await get_user_by_id(db, target_user_id)
    if not target_user:
        raise AppException(400, "INVALID_TARGET", "User does not exist")

    stmt = (
        select(Chat)
        .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
        .where(Chat.chat_type == ChatType.PRIVATE)
        .group_by(Chat.id)
        .having(
            func.count(ChatParticipant.chat_id) == 2
        )
        .having(
            func.sum(
                (ChatParticipant.user_id == current_user_id).cast(Integer)
            ) > 0
        )
        .having(
            func.sum(
                (ChatParticipant.user_id == target_user_id).cast(Integer)
            ) > 0
        )
        .options(selectinload(Chat.participants))
    )

    result = await db.execute(stmt)
    chat = result.scalar_one_or_none()

    if chat:
        return chat

    new_chat = Chat(chat_type=ChatType.PRIVATE)
    db.add(new_chat)
    await db.flush()

    prt1 = ChatParticipant(chat_id=new_chat.id, user_id=current_user_id, role=ParticipantRole.MEMBER)
    prt2 = ChatParticipant(chat_id=new_chat.id, user_id=target_user_id, role=ParticipantRole.MEMBER)

    db.add_all([prt1, prt2])
    await db.commit()

    await db.refresh(new_chat, ['participants'])
    return new_chat


async def get_user_chats(
        db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0
) -> tuple[list[Chat], int]:
    count_stmt = (
        select(func.count())
        .select_from(ChatParticipant)
        .where(ChatParticipant.user_id == user_id)
    )
    total_count = await db.scalar(count_stmt)

    stmt = (
        select(Chat)
        .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
        .where(ChatParticipant.user_id == user_id)
        .options(selectinload(Chat.participants))
        .order_by(Chat.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    res = await db.execute(stmt)
    chats = list(res.scalars().all())

    return chats, total_count


async def update_chat_updated_at(
        db: AsyncSession,
        chat_id: uuid.UUID
):
    stmt = (update(Chat).where(Chat.id == chat_id).values(updated_at=func.now()))
    res = await db.execute(stmt)
    await db.commit()

    return res.rowcount


async def get_chat_participants_ids(db: AsyncSession, chat_id: uuid.UUID):
    stmt = select(ChatParticipant.user_id).where(ChatParticipant.chat_id == chat_id)
    res = await db.execute(stmt)

    return res.scalars().all()


async def update_participant_last_read(
        db: AsyncSession,
        chat_id: uuid.UUID,
        user_id: uuid.UUID,
        last_read_message_id: str
):
    stmt = (
        update(ChatParticipant)
        .where(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == user_id,
        )
        .values(last_read_message_id=last_read_message_id)
    )

    await db.execute(stmt)
    await db.commit()


async def get_chat_participants_by_user(db: AsyncSession, user_id: uuid.UUID):
    stmt = (
        select(ChatParticipant)
        .where(ChatParticipant.user_id == user_id)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


async def get_user_chats_with_unread(db: AsyncSession, mongo_db: AsyncIOMotorDatabase, user_id: uuid.UUID):
    participants = await get_chat_participants_by_user(db, user_id)

    collection = mongo_db["messages"]
    result_chats = []

    # TODO: Aggregate without N+1 (count + find)
    for p in participants:
        query = {
            "chat_id": p.chat_id,
            "sender_id": {"$ne": p.user_id}
        }

        if p.last_read_message_id:
            query["_id"] = {"$gt": objectify_id(p.last_read_message_id)}

        unread_count = await collection.count_documents(query)

        last_msg_cursor = collection.find({"chat_id": p.chat_id}).sort("_id", -1).limit(1)
        last_msg = await last_msg_cursor.to_list(length=1)

        result_chats.append({
            "chat_id": p.chat_id,
            "unread_count": unread_count,
            "last_message": last_msg[0] if last_msg else None
        })

    return result_chats
