from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.exceptions import AppException
from app.core.security import get_password_hash
from app.domains.users.models.user import User
from app.domains.users.schemas.user_schemas import UserCreate


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_in: UserCreate) -> User | None:
    existing_user = await get_user_by_username(db, user_in.username)
    if existing_user:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="USER_ALREADY_EXISTS",
            message="User with that username already exists."
        )

    user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        public_key=user_in.public_key,
        encrypted_private_key=user_in.encrypted_private_key
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user
