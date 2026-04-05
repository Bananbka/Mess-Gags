from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings


class MongoClient:
    client: AsyncIOMotorClient = None
    db = None


mongo_client = MongoClient()


async def connect_to_mongo():
    mongo_client.client = AsyncIOMotorClient(settings.MONGO_URL, uuidRepresentation="standard")
    mongo_client.db = mongo_client.client[settings.MONGO_DB_NAME]
    print("Connected to MongoDB via Motor (Pure).")


async def close_mongo_connection():
    if mongo_client.client:
        mongo_client.client.close()
    print("MongoDB connection closed.")


def get_mongo_db():
    return mongo_client.db
