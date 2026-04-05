import time

import jwt
from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.responses import SuccessResponse
from app.core.security import create_access_token, verify_password
from app.domains.users.dependencies import oauth2_scheme, get_current_user
from app.domains.users.models.user import User
from app.domains.users.schemas.user_schemas import TokenResponse, UserCreate, UserLogin, UserResponse
from app.domains.users.services import user_service
from app.infrastructure.postgres import get_db
from app.infrastructure.redis import get_redis

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=SuccessResponse[TokenResponse])
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await user_service.create_user(db, user_in)

    access_token = create_access_token(data={"sub": user.username})

    return SuccessResponse(
        data=TokenResponse(access_token=access_token, user=user)
    )


@router.post("/login", response_model=SuccessResponse[TokenResponse])
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await user_service.get_user_by_username(db, user_in.username)

    if not user or not verify_password(user_in.password, user.hashed_password):
        raise AppException(401, "INVALID_CREDENTIALS", "Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})

    return SuccessResponse(
        data=TokenResponse(access_token=access_token, user=user)
    )


@router.post("/logout", response_model=SuccessResponse[dict])
async def logout(
        token: str = Depends(oauth2_scheme),
        redis: Redis = Depends(get_redis)
):
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")

        ttl = int(exp - time.time())
        if ttl > 0:
            await redis.setex(f"blacklist:{token}", ttl, "revoked")

    except jwt.PyJWTError:
        pass

    return SuccessResponse(data={"message": "Token deactivated"})


@router.get("/me", response_model=SuccessResponse[UserResponse])
async def me(current_user: User = Depends(get_current_user)):
    return SuccessResponse(data=current_user)
