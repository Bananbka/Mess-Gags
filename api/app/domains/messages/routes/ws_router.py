import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from redis.asyncio import Redis

from app.domains.users.dependencies import get_ws_current_user
from app.domains.users.models import User
from app.infrastructure.redis import get_redis

ws_router = APIRouter()


async def listen_to_redis(pubsub, websocket: WebSocket):
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                text_data = message["data"]
                await websocket.send_text(text_data)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"REDIS TASK ERROR: {e}")


@ws_router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket,
                             user: User = Depends(get_ws_current_user),
                             redis: Redis = Depends(get_redis)):
    await websocket.accept()

    pubsub = redis.pubsub()
    channel_name = f"user:{user.id}"
    await pubsub.subscribe(channel_name)

    redis_task = asyncio.create_task(listen_to_redis(pubsub, websocket))

    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        pass

    finally:
        redis_task.cancel()
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()
