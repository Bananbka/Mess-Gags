import uuid

from redis.asyncio import Redis

from app.domains.chats.models import Chat
from app.domains.chats.schemas.chat_schemas import ChatResponse
from app.domains.messages.schemas.ws_schemas import WSMessageEnvelope, WSEventType


async def send_chat_created_message(redis: Redis, chat: Chat, user_id: uuid.UUID, participant_ids: list[uuid.UUID]):
    chat_dict = ChatResponse.model_validate(chat).model_dump(mode='json')

    ws_envelope = WSMessageEnvelope(
        event_type=WSEventType.CHAT_CREATED,
        chat_id=chat.id,
        user_id=user_id,
        payload={
            "message": f"Group '{chat.title}' has been created.",
            "chat": chat_dict
        }
    )
    event_json = ws_envelope.model_dump_json()
    pids = set(participant_ids) | {user_id}

    for user_id in pids:
        await redis.publish(f"user:{user_id}", event_json)
