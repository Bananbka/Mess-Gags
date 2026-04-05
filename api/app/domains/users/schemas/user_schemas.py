import uuid
from pydantic import BaseModel, Field, ConfigDict, EmailStr


class UserCreate(BaseModel):
    username: str = Field(..., min_length=6, max_length=50)
    password: str = Field(..., min_length=8, max_length=72)
    email: EmailStr
    public_key: str
    encrypted_private_key: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr
    public_key: str
    bio: str | None = None
    avatar: str | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PasswordRestore(BaseModel):
    username: str
    email: EmailStr
