import uuid

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select, func, Integer, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, aliased

from app.core.exceptions import AppException
from app.domains.chats.models import Chat, ChatParticipant, ChatType, ParticipantRole, Contact
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
) -> tuple[list, int]:
    count_stmt = (
        select(func.count())
        .select_from(ChatParticipant)
        .where(ChatParticipant.user_id == user_id)
    )
    total_count = await db.scalar(count_stmt)

    if total_count == 0:
        return [], 0

    me = aliased(ChatParticipant)
    other = aliased(ChatParticipant)

    stmt = (
        select(
            Chat,
            me.last_read_message_id,
            Contact.alias_name.label("partner_alias")
        )
        .join(me, and_(Chat.id == me.chat_id, me.user_id == user_id))
        .outerjoin(other, and_(Chat.id == other.chat_id, other.user_id != user_id))
        .outerjoin(
            Contact,
            and_(
                Contact.owner_id == user_id,
                Contact.contact_id == other.user_id
            )
        )
        .options(
            selectinload(Chat.participants).selectinload(ChatParticipant.user))
        .order_by(Chat.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )

    res = await db.execute(stmt)

    chats = []
    for row in res.all():
        chat = row.Chat
        chat.last_read_message_id = row.last_read_message_id
        chat.partner_alias = row.partner_alias
        chats.append(chat)

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


async def enrich_chats_with_mongo_data(
        mongo_db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        pg_chats: list
) -> list[dict]:
    chat_ids = [chat.id for chat in pg_chats]

    unread_branches = []
    for chat in pg_chats:
        chat_match = {"$eq": ["$chat_id", chat.id]}
        sender_match = {"$ne": ["$sender_id", user_id]}

        if getattr(chat, "last_read_message_id", None) and ObjectId.is_valid(chat.last_read_message_id):
            read_match = {"$gt": ["$_id", ObjectId(chat.last_read_message_id)]}
            is_unread = {"$and": [chat_match, sender_match, read_match]}
        else:
            is_unread = {"$and": [chat_match, sender_match]}

        unread_branches.append({
            "case": is_unread,
            "then": 1
        })

    pipeline = [
        {"$match": {"chat_id": {"$in": chat_ids}}},
        {"$sort": {"_id": -1}},
        {"$group": {
            "_id": "$chat_id",
            "last_message": {"$first": "$$ROOT"},
            "unread_count": {
                "$sum": {"$switch": {"branches": unread_branches, "default": 0}}
            }
        }}
    ]

    collection = mongo_db["messages"]
    aggregated_data = await collection.aggregate(pipeline).to_list(None)

    mongo_dict = {doc["_id"]: doc for doc in aggregated_data}

    result = []
    for chat in pg_chats:
        stats = mongo_dict.get(chat.id, {"unread_count": 0, "last_message": None})

        last_msg = stats["last_message"]
        if last_msg and "_id" in last_msg:
            last_msg["_id"] = str(last_msg["_id"])

        display_name = chat.title
        partner_avatar = None

        if chat.chat_type == ChatType.PRIVATE:
            partner = next((p.user for p in chat.participants if p.user_id != user_id), None)

            if partner:
                partner_avatar = partner.avatar_url
                display_name = getattr(chat, "partner_alias", None) or partner.full_name

        result.append({
            "id": chat.id,
            "title": display_name,
            "avatar_url": partner_avatar,
            "chat_type": chat.chat_type,
            "unread_count": stats["unread_count"],
            "last_message": last_msg,
            "created_at": chat.created_at,
            "updated_at": chat.updated_at,
        })

    return result
