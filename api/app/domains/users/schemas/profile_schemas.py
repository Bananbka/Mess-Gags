from pydantic import BaseModel


class ProfileRequestSchema(BaseModel):
    username: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
