import time

import jwt
from fastapi import APIRouter, Depends
from fastapi import Response, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.responses import SuccessResponse
from app.core.security import create_access_token, verify_password, create_refresh_token
from app.domains.users.dependencies import oauth2_scheme, get_current_user
from app.domains.users.models.user import User
from app.domains.users.schemas.user_schemas import UserCreate, UserLogin, UserResponse
from app.domains.users.services import user_service
from app.infrastructure.postgres import get_db
from app.infrastructure.redis import get_redis

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=SuccessResponse[UserResponse])
async def register(user_in: UserCreate, response: Response, db: AsyncSession = Depends(get_db)):
    user = await user_service.create_user(db, user_in)

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=1800,
        samesite="lax",
        secure=False,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=604800,
        samesite="lax",
        secure=False,
    )

    return SuccessResponse(data=user)


@router.post("/login", response_model=SuccessResponse[UserResponse])
async def login(user_in: UserLogin, response: Response, db: AsyncSession = Depends(get_db)):
    user = await user_service.get_user_by_username(db, user_in.username)

    if not user or not verify_password(user_in.password, user.hashed_password):
        raise AppException(401, "INVALID_CREDENTIALS", "Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=1800,
        samesite="lax",
        secure=False,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=604800,
        samesite="lax",
        secure=False,
    )

    return SuccessResponse(data=user)


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


@router.post("/refresh", response_model=SuccessResponse[dict])
async def refresh(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise AppException(401, "NO_REFRESH_TOKEN", "There is no refresh token in cookies.")

    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if not payload.get("refresh"):
            raise AppException(401, "INVALID_TOKEN", "Invalid token data.")

        new_access = create_access_token(data={"sub": payload.get("username")})
        response.set_cookie(
            key="access_token",
            value=new_access,
            httponly=True,
            max_age=1800,
            samesite="lax",
            secure=False,
        )
        return SuccessResponse(data={"message": "Token has been successfully updated."})
    except:
        raise AppException(401, "INVALID_REFRESH", "Session error.")


@router.get("/me", response_model=SuccessResponse[UserResponse])
async def me(current_user: User = Depends(get_current_user)):
    return SuccessResponse(data=current_user)
