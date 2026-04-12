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
    MINIO_BUCKET_NAME: str = "chat-attachments"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    # EMAIL
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_NAME: str = "Mess&Gags Security"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
