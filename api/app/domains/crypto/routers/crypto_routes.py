import uuid

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import SuccessResponse
from app.domains.crypto.schemas.crypto_schemas import (
    IdentityPublishRequest,
    OwnIdentityResponse,
    PrekeyRotateRequest,
    PublicKeyResponse,
    SafetyNumberResponse,
    UserKeysRequest,
)
from app.domains.crypto.services import identity_service
from app.domains.users.dependencies import get_current_user
from app.domains.users.models import User
from app.infrastructure.postgres import get_db

router = APIRouter(prefix="/crypto", tags=["Crypto"])


@router.post("/identity", response_model=SuccessResponse[PublicKeyResponse])
async def publish_identity(
        data: IdentityPublishRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """Publish or rotate this device's identity keys."""
    key = await identity_service.publish_identity(db, user.id, data)
    return SuccessResponse(data=key)


@router.get("/identity/me", response_model=SuccessResponse[list[OwnIdentityResponse]])
async def get_my_identities(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """Own key material including the wrapped private bundle, for unlocking after login."""
    keys = await identity_service.get_own_identities(db, user.id)
    return SuccessResponse(data=keys)


@router.put("/identity/prekey", response_model=SuccessResponse[PublicKeyResponse])
async def rotate_prekey(
        data: PrekeyRotateRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """Rotate the medium-term signed prekey. Does not invalidate existing key grants."""
    key = await identity_service.rotate_prekey(db, user.id, data)
    return SuccessResponse(data=key)


@router.post("/keys/batch", response_model=SuccessResponse[list[PublicKeyResponse]])
async def get_keys_batch(
        data: UserKeysRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """Batch-fetch public keys. Called before wrapping group keys for a chat's members."""
    keys = await identity_service.get_active_keys_for_users(db, data.user_ids)
    return SuccessResponse(data=keys, meta={"count": len(keys)})


@router.get("/safety-number/{peer_user_id}", response_model=SuccessResponse[SafetyNumberResponse])
async def get_safety_number(
        peer_user_id: uuid.UUID = Path(..., description="The user to verify against"),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """Fingerprint for out-of-band verification.

    Users compare this through a channel the server does not control (in person, by voice). It is
    the only defence against the server substituting a public key, and it must visibly change if
    a peer's key ever changes.
    """
    number = await identity_service.compute_safety_number(db, user.id, peer_user_id)

    return SuccessResponse(data=SafetyNumberResponse(
        user_id=user.id,
        peer_user_id=peer_user_id,
        safety_number=number,
    ))
