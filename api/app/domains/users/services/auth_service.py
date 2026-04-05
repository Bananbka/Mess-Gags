import random
import uuid

from redis.asyncio import Redis


async def generate_otp(redis: Redis, user_id: uuid.UUID) -> str:
    otp = f"{random.randint(100000, 999999)}"
    await redis.setex(f"otp:{user_id}", 900, otp)
    return otp
