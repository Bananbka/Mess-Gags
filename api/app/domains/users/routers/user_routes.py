from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import SuccessResponse
from app.domains.users.dependencies import get_current_user
from app.domains.users.models import User
from app.domains.users.schemas.user_schemas import UserSearchResponse
from app.domains.users.services.user_service import find_users_by_username
from app.infrastructure.postgres import get_db

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/search", response_model=SuccessResponse[list[UserSearchResponse]])
async def search_users(
        query: str = Query(..., min_length=1, description="Search query for username"),
        limit: int = Query(20, ge=1, le=50),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    users = await find_users_by_username(db, query, user.id, limit)
    return SuccessResponse(data=users)