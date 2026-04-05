import uuid

from sqlalchemy import select, func, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.domains.chats.models import Chat, ChatParticipant, ChatType, ParticipantRole
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
