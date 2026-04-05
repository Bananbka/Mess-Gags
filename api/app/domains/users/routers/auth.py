import time

import jwt
from fastapi import APIRouter, Depends
from fastapi import Response, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.responses import SuccessResponse
from app.core.security import create_access_token, verify_password, create_refresh_token, set_token_cookie, \
    delete_token_cookies, get_password_hash
from app.domains.users.dependencies import get_current_user
from app.domains.users.models.user import User
from app.domains.users.schemas.user_schemas import UserCreate, UserLogin, UserResponse, PasswordForgot, PasswordReset
from app.domains.users.services import user_service
from app.domains.users.services.auth_service import generate_otp, check_otp
from app.domains.users.services.user_service import get_user_by_email_and_username, get_user_by_username
from app.domains.users.tasks import send_reset_password_email
from app.infrastructure.postgres import get_db
from app.infrastructure.redis import get_redis

router = APIRouter(prefix="/auth", tags=["Authentication"])


### AUTHENTICATION
@router.post("/register", response_model=SuccessResponse[UserResponse])
async def register(user_in: UserCreate, response: Response, db: AsyncSession = Depends(get_db)):
    user = await user_service.create_user(db, user_in)

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    set_token_cookie(response, access_token, "access")
    set_token_cookie(response, refresh_token, "refresh")

    return SuccessResponse(data=user)


@router.post("/login", response_model=SuccessResponse[UserResponse])
async def login(user_in: UserLogin, response: Response, db: AsyncSession = Depends(get_db)):
    user = await user_service.get_user_by_username(db, user_in.username)

    if not user or not verify_password(user_in.password, user.hashed_password):
        raise AppException(401, "INVALID_CREDENTIALS", "Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    set_token_cookie(response, access_token, "access")
    set_token_cookie(response, refresh_token, "refresh")

    return SuccessResponse(data=user)


@router.post("/logout", response_model=SuccessResponse[dict])
async def logout(
        request: Request,
        response: Response,
        redis: Redis = Depends(get_redis)
):
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            exp = payload.get("exp")

            ttl = int(exp - time.time())
            if ttl > 0:
                await redis.setex(f"blacklist:{token}", ttl, "revoked")

        except jwt.PyJWTError:
            pass

    delete_token_cookies(response)
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
        set_token_cookie(response, new_access, "access")

        return SuccessResponse(data={"message": "Token has been successfully updated."})
    except:
        raise AppException(401, "INVALID_REFRESH", "Session error.")


### PROFILE
@router.get("/me", response_model=SuccessResponse[UserResponse])
async def me(current_user: User = Depends(get_current_user)):
    return SuccessResponse(data=current_user)


### RESTORE
@router.post("/forgot-password", response_model=SuccessResponse[dict])
async def forgot_password(
        user_data: PasswordForgot,
        db: AsyncSession = Depends(get_db),
        redis: Redis = Depends(get_redis)
):
    user = await get_user_by_email_and_username(db, user_data.username, user_data.email)
    if not user:
        raise AppException(404, "UNKNOWN_USER", "There is no user with such credentials.")

    otp = await generate_otp(redis, user.id)

    send_reset_password_email.delay(user.email, otp)
    return SuccessResponse(data={"message": "Password reset email sent."})


@router.post("/reset-password", response_model=SuccessResponse[dict])
async def reset_password(
        user_data: PasswordReset,
        db: AsyncSession = Depends(get_db),
        redis: Redis = Depends(get_redis)
):
    user = await get_user_by_username(db, user_data.username)
    if not user:
        raise AppException(404, "UNKNOWN_USER", "There is no user with such credentials.")

    is_valid = await check_otp(redis, user.id, user_data.otp)
    if not is_valid:
        raise AppException(404, "INVALID_OTP", "Invalid OTP.")

    user.hashed_password = get_password_hash(user_data.new_password)
    user.public_key = user_data.new_public_key
    user.encrypted_private_key = user_data.new_encrypted_private_key

    await db.commit()

    await redis.setex(f"force_logout:{user.id}", 604800, int(time.time()))

    return SuccessResponse(data={"message": "Password and keys was successfully updated."})
