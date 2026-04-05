from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import mongo_client

from app.core.config import settings


class MongoClient:
    client: AsyncIOMotorClient = None
    db = None


mongo_client = MongoClient()


async def connect_to_mongo():
    mongo_client.client = AsyncIOMotorClient(settings.MONGO_URL)
    mongo_client.db = mongo_client.client[settings.MONGO_DB_NAME]
    print("Connect to MongoDB.")


async def close_mongo_connection():
    mongo_client.client.close()
    print("MongoDB connection closed")


def get_mongo_db():
    return mongo_client.db
