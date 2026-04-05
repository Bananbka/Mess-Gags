from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Postgres
    DATABASE_URL: str

    # MongoDB
    MONGO_URL: str
    MONGO_DB_NAME: str = "messenger_db"

    # Redis
    REDIS_URL: str

    # MinIO
    MINIO_URL: str
    MINIO_USER: str
    MINIO_PASSWORD: str
    MINIO_BUCKET_NAME: str = "messenger-media"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
