from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import SuccessResponse
from app.domains.messages.schemas.messages_schemas import MessageResponse, MessageCreateRequest
from app.domains.messages.services.messages_service import send_message
from app.domains.users.dependencies import get_current_user
from app.domains.users.models import User
from app.infrastructure.mongo import get_mongo_db
from app.infrastructure.postgres import get_db

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/", response_model=SuccessResponse[MessageResponse])
async def create_message(
        message_in: MessageCreateRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db)

):
    new_message = await send_message(db, mongo_db, user.id, message_in)
    return SuccessResponse(data=new_message)
