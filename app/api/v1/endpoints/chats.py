from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.chat import Chat, ChatCreate
from app.db.repositories.chats import chat_repository
from app.auth.deps import get_current_user

router = APIRouter()

@router.get("/", response_model=List[Chat])
async def get_chats(current_user = Depends(get_current_user)):
    """Get all chats for the current user"""
    try:
        chats = await chat_repository.get_by_user(current_user['email'])
        return chats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/", response_model=Chat)
async def create_chat(
    chat: ChatCreate,
    current_user = Depends(get_current_user)
):
    """Create a new chat"""
    try:
        return await chat_repository.create({
            **chat.model_dump(),
            "user_id": current_user['email']
        })
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user = Depends(get_current_user)
):
    """Delete a chat"""
    success = await chat_repository.delete(chat_id, current_user['email'])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or you don't have permission to delete it"
        )
    return {"message": "Chat deleted successfully"} 