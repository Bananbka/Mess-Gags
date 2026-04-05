from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import SuccessResponse
from app.domains.chats.schemas.chat_schemas import ChatResponse, PrivateChatCreateRequest
from app.domains.chats.services.chat_services import get_or_create_private_chat, get_user_chats
from app.domains.users.dependencies import get_current_user
from app.domains.users.models import User
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


@router.post('/', response_model=SuccessResponse[list[ChatResponse]])
async def get_chats(
        limit: int = 20,
        offset: int = 0,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    chats, total_count = await get_user_chats(db, user.id, limit, offset)

    meta = {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total_count
    }

    return SuccessResponse(data=chats, meta=meta)
