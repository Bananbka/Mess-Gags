import uuid

import phonenumbers
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator


class UserCreate(BaseModel):
    username: str = Field(..., min_length=6, max_length=50)
    password: str = Field(..., min_length=8, max_length=72)
    email: EmailStr
    phone_number: str
    public_key: str
    encrypted_private_key: str

    @field_validator('phone_number')
    @classmethod
    def validate_phone(cls, v: str):
        try:
            parsed_number = phonenumbers.parse(v)

            if not phonenumbers.is_valid_number(parsed_number):
                raise ValueError('Invalid phone number for this country.')

            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)

        except phonenumbers.NumberParseException:
            raise ValueError('Invalid phone number format.')


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr
    phone_number: str
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


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=72)
    new_encrypted_private_key: str
