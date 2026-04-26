import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, insert, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.core.responses import SuccessResponse
from app.domains.chats.models import ChatParticipant, ChatFolder, FolderItem
from app.domains.chats.schemas.folder_schemas import FolderResponse, FolderCreateRequest
from app.domains.messages.services.messages_service import is_user_in_all_chats
from app.domains.users.dependencies import get_current_user
from app.domains.users.models import User
from app.infrastructure.postgres import get_db

router = APIRouter(prefix="/chat-folder", tags=["Folders"])


@router.post("/", response_model=SuccessResponse[FolderResponse])
async def create_folder(
        data: FolderCreateRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    stmt = select(func.count()).select_from(ChatParticipant).where(
        ChatParticipant.chat_id.in_(data.chat_ids),
        ChatParticipant.user_id == user.id
    )
    res = await db.execute(stmt)

    cp = res.scalar_one()
    if cp != len(data.chat_ids):
        raise AppException(403, "FORBIDDEN", "You don't have permission to access some of chats")

    folder = ChatFolder(user_id=user.id, title=data.title)
    db.add(folder)
    await db.flush()

    chat_ids = set(data.chat_ids)
    items_to_create = [{"chat_id": chat_id, "folder_id": folder.id} for chat_id in chat_ids]

    if items_to_create:
        await db.execute(insert(FolderItem), items_to_create)

    await db.commit()

    await db.refresh(folder, attribute_names=['items'])
    return SuccessResponse(data=folder)


@router.get("/{folder_id}", response_model=SuccessResponse[FolderResponse])
async def get_folder(
        folder_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(ChatFolder)
        .where(ChatFolder.id == folder_id, ChatFolder.user_id == user.id)
        .options(selectinload(ChatFolder.items))
    )
    res = await db.execute(stmt)
    folder = res.scalar_one_or_none()

    if folder is None:
        raise AppException(404, "NOT_FOUND", "There is no your folders with such id.")

    return SuccessResponse(data=folder)


@router.get("/", response_model=SuccessResponse[list[FolderResponse]])
async def get_folders(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(ChatFolder)
        .where(ChatFolder.user_id == user.id)
        .options(selectinload(ChatFolder.items))
        .order_by(ChatFolder.created_at.asc())
    )
    res = await db.execute(stmt)
    folders = res.scalars().all()

    return SuccessResponse(data=folders)


@router.patch("/{folder_id}", response_model=SuccessResponse[FolderResponse])
async def update_folder(
        folder_id: uuid.UUID,
        data: FolderCreateRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    update_data = data.model_dump(exclude_unset=True)

    stmt = (
        select(ChatFolder)
        .where(ChatFolder.id == folder_id, ChatFolder.user_id == user.id)
        .options(selectinload(ChatFolder.items))
    )

    res = await db.execute(stmt)
    folder = res.scalar_one_or_none()

    if folder is None:
        raise AppException(404, "NOT_FOUND", "There is no your folders with such id.")

    if not update_data:
        return SuccessResponse(data=folder)

    if 'title' in update_data:
        folder.title = update_data['title']

    if 'chat_ids' in update_data:
        current_chat_ids = {item.chat_id for item in folder.items}
        new_chat_ids = set(update_data['chat_ids'])

        if not await is_user_in_all_chats(db, user.id, new_chat_ids):
            raise AppException(403, "FORBIDDEN", "You don't have permission to access some of chats")

        to_add = new_chat_ids - current_chat_ids
        to_delete = current_chat_ids - new_chat_ids

        if to_delete:
            await db.execute(
                delete(FolderItem).where(
                    FolderItem.folder_id == folder.id,
                    FolderItem.chat_id.in_(to_delete)
                )
            )

        if to_add:
            items_to_create = [
                {"chat_id": chat_id, "folder_id": folder.id}
                for chat_id in to_add
            ]
            await db.execute(insert(FolderItem), items_to_create)

    await db.commit()

    await db.refresh(folder, attribute_names=['items'])

    return SuccessResponse(data=folder)


@router.delete("/{folder_id}", response_model=SuccessResponse[dict])
async def delete_folder(
        folder_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    stmt = delete(ChatFolder).where(
        ChatFolder.id == folder_id,
        ChatFolder.user_id == user.id
    )

    res = await db.execute(stmt)

    if res.rowcount == 0:
        raise AppException(404, "NOT_FOUND", "There is no your folders with such id.")

    await db.commit()

    return SuccessResponse(data={"message": "Folder deleted"})
