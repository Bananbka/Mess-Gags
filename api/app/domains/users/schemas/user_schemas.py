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


class PasswordForgot(BaseModel):
    username: str
    email: EmailStr


class PasswordReset(BaseModel):
    username: str
    otp: str = Field(..., min_length=6, max_length=6)

    new_password: str = Field(..., min_length=8, max_length=72)
    new_public_key: str
    new_encrypted_private_key: str
