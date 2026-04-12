import uuid

from fastapi import APIRouter, Depends, Path, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import SuccessResponse
from app.domains.chats.schemas.chat_schemas import ChatResponse, PrivateChatCreateRequest
from app.domains.chats.services import chat_services
from app.domains.chats.services.chat_services import get_or_create_private_chat, get_user_chats
from app.domains.messages.schemas.messages_schemas import MessageResponse
from app.domains.messages.services import messages_service
from app.domains.users.dependencies import get_current_user
from app.domains.users.models import User
from app.infrastructure.mongo import get_mongo_db
from app.infrastructure.postgres import get_db

router = APIRouter(prefix='/chats', tags=['Chats'])


@router.post('/private', response_model=SuccessResponse[ChatResponse])
async def private_chat(
        data: PrivateChatCreateRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    chat = await get_or_create_private_chat(db, current_user.id, data.target_user_id)
    return SuccessResponse(data=chat)


@router.get('/', response_model=SuccessResponse[list[ChatResponse]])
async def get_chats(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    chats_from_pg, total_count = await get_user_chats(db, user.id, limit, offset)

    if not chats_from_pg:
        return SuccessResponse(
            data=[],
            meta={"total": total_count, "limit": limit, "offset": offset, "has_more": False}
        )

    enriched_chats = await chat_services.enrich_chats_with_mongo_data(
        mongo_db, user.id, chats_from_pg
    )

    meta = {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total_count
    }

    return SuccessResponse(data=enriched_chats, meta=meta)


@router.get('/{chat_id}/messages', response_model=SuccessResponse[list[MessageResponse]])
async def get_chat_messages(
        chat_id: uuid.UUID = Path(..., description="Chat ID"),
        limit: int = Query(50, ge=1, le=100),
        before_id: str | None = Query(None, description="_id of the oldest loaded message."),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    messages = await messages_service.get_chat_messages(db, mongo_db, user.id, chat_id, limit, before_id)
    return SuccessResponse(data=messages)
