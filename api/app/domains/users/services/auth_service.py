import random
import uuid

from redis.asyncio import Redis


async def generate_otp(redis: Redis, user_id: uuid.UUID) -> str:
    redis_key = f"password_reset:{user_id}"
    otp = f"{random.randint(100000, 999999)}"
    await redis.setex(redis_key, 900, otp)
    return otp


async def check_otp(redis: Redis, user_id: uuid.UUID, otp: str) -> bool:
    redis_key = f"password_reset:{user_id}"
    true_otp = await redis.get(redis_key)

    if true_otp and true_otp == otp:
        await redis.delete(redis_key)
        return True

    return False
