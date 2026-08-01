import datetime
import enum
import uuid

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.config import settings


class Attachment(BaseModel):
    """A message attachment.

    `url` is validated to be a single object key inside the message bucket. Without this the
    value is entirely client-controlled and flows into MinIO deletion in `delete_message`,
    which would let a user delete arbitrary objects belonging to other users.
    """
    url: str
    name: str = Field(..., max_length=255)
    size: int = Field(..., ge=0)
    content_type: str = Field(..., max_length=255)

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        prefix = f"{settings.MINIO_URL}/{settings.MINIO_MESSAGE_BUCKET}/"
        if not v.startswith(prefix):
            raise ValueError('Attachment url must point at the message attachments bucket.')

        object_key = v[len(prefix):]
        if not object_key or "/" in object_key:
            raise ValueError('Attachment url must reference a single object key.')

        return v


class ContentFormat(str, enum.Enum):
    """How a message's content is encoded.

    Persisted on the document rather than derived at read time. The previous `is_encrypted` bool
    was computed independently on the send and read paths and the two disagreed — the send path
    silently dropped it and always reported True.
    """
    LEGACY_PLAINTEXT = "legacy_plaintext"   # group/channel messages from before encryption
    LEGACY_RSA = "legacy_rsa"               # private chats under the old RSA scheme
    SENDER_KEYS_V1 = "sender_keys_v1"       # current: envelope + sender-key ratchet

    @property
    def is_encrypted(self) -> bool:
        return self is not ContentFormat.LEGACY_PLAINTEXT


class MessageEnvelope(BaseModel):
    """Sealed message content. See app/domains/crypto/reference/envelope.py for the format.

    chat_id and sender_id are deliberately absent: they are bound into the AAD but taken from the
    request path and the JWT, never from client-supplied envelope fields.
    """
    v: int = Field(1, ge=1)
    alg: str = Field(..., max_length=32)
    epoch: int = Field(..., ge=0)
    skid: uuid.UUID                     # sender_key_id
    idx: int = Field(..., ge=0)         # chain index
    n: str = Field(..., max_length=32)  # nonce, b64u
    ct: str                             # ciphertext || GCM tag, b64u
    sig: str = Field(..., max_length=128)  # Ed25519, b64u


class MessageDocument(BaseModel):
    chat_id: uuid.UUID
    sender_id: uuid.UUID

    # Exactly one of these carries the content, selected by content_format.
    encrypted_content: str | None = None
    envelope: MessageEnvelope | None = None
    content_format: ContentFormat = ContentFormat.LEGACY_PLAINTEXT

    reply_to_message_id: str | None = None

    attachments: list[dict] | None = None

    is_read: bool = False
    is_pinned: bool = False
    is_edited: bool = False

    created_at: datetime.datetime


class MessageResponse(BaseModel):
    id: str = Field(alias="_id")
    chat_id: uuid.UUID
    sender_id: uuid.UUID

    encrypted_content: str | None = None
    envelope: MessageEnvelope | None = None
    content_format: ContentFormat = ContentFormat.LEGACY_PLAINTEXT

    reply_to_message_id: str | None = None
    created_at: datetime.datetime

    attachments: list[dict] | None = None

    is_read: bool = False
    is_pinned: bool = False
    is_edited: bool = False

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @computed_field
    @property
    def is_encrypted(self) -> bool:
        """Retained for API compatibility, now derived from the persisted format rather than
        recomputed from chat_type on each path."""
        return self.content_format.is_encrypted


class MessageCreateRequest(BaseModel):
    """Send a message. Supply `envelope` (v1) or `encrypted_content` (legacy), never both."""
    chat_id: uuid.UUID

    encrypted_content: str | None = None
    envelope: MessageEnvelope | None = None

    reply_to_message_id: str | None = None
    attachments: list[Attachment] | None = None

    @model_validator(mode="after")
    def check_exactly_one_content(self):
        if (self.envelope is None) == (self.encrypted_content is None):
            raise ValueError("provide exactly one of 'envelope' or 'encrypted_content'")
        return self


class MessageUpdateRequest(BaseModel):
    """Edit a message.

    A v1 edit must be sealed under a FRESH chain index. Re-encrypting under an already-used
    message key would repeat a (key, nonce) pair, which is catastrophic for AES-GCM — it leaks the
    XOR of both plaintexts and can expose the authentication subkey.
    """
    encrypted_content: str | None = None
    envelope: MessageEnvelope | None = None

    @model_validator(mode="after")
    def check_exactly_one_content(self):
        if (self.envelope is None) == (self.encrypted_content is None):
            raise ValueError("provide exactly one of 'envelope' or 'encrypted_content'")
        return self
