import jwt
from aiohttp import payload
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from redis import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import settings
from app.core.exceptions import AppException
from app.domains.users.models.user import User
from app.domains.users.services.user_service import get_user_by_username
from app.infrastructure.postgres import get_db
from app.infrastructure.redis import get_redis

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
        redis: Redis = Depends(get_redis)
) -> User:
    is_blacklisted = await redis.get(f"blacklist:{token}")
    if is_blacklisted:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="TOKEN_REVOKED",
            message="Token blacklisted. Please log in again.",
        )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise AppException(401, "INVALID_TOKEN", "Invalid token data.")
    except jwt.ExpiredSignatureError:
        raise AppException(401, "TOKEN_EXPIRED", "Token is expired.")
    except jwt.PyJWTError:
        raise AppException(401, "INVALID_TOKEN", "Invalid token.")

    user = await get_user_by_username(db, username)
    if user is None:
        raise AppException(404, "USER_NOT_FOUNR", "User is not found.")

    return user
