from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
from app.auth.deps import get_current_user
from app.services.rag_service import RAGService
from app.db.repositories.chats import chat_repository
from app.db.repositories.documents import document_repository
from app.db.repositories.messages import message_repository

logger = logging.getLogger(__name__)

router = APIRouter()

# Models
class ChatBase(BaseModel):
    title: str
    knowledge_base_ids: List[str]

class ChatCreate(ChatBase):
    pass

class Chat(ChatBase):
    id: str
    user_id: str
    created_at: str
    last_modified: str

class Message(BaseModel):
    id: str
    chat_id: str
    content: str
    role: str
    created_at: str

class ChatMessageCreate(BaseModel):
    content: str

# Chat endpoints
@router.get("/", response_model=List[Chat])
async def get_chats(current_user: dict = Depends(get_current_user)):
    return await chat_repository.get_by_user(current_user['email'])

@router.post("/", response_model=Chat)
async def create_chat(
    chat: ChatCreate,
    current_user: dict = Depends(get_current_user)
):
    return await chat_repository.create({
        **chat.model_dump(),
        "user_id": current_user['email']
    })

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: dict = Depends(get_current_user)
):
    # First verify chat belongs to user
    chat = await chat_repository.get_chat(chat_id, current_user['email'])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Delete associated messages first
    messages_deleted = await message_repository.delete_by_chat_id(chat_id, current_user['email'])
    if not messages_deleted:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete chat messages"
        )
        
    # Delete the chat
    success = await chat_repository.delete(chat_id, current_user['email'])
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete chat"
        )
    
    return {"message": "Chat and associated messages deleted successfully"}

# Message endpoints
@router.get("/{chat_id}/messages", response_model=List[Message])
async def get_messages(
    chat_id: str,
    current_user: dict = Depends(get_current_user)
):
    # First verify chat belongs to user
    chat = await chat_repository.get_chat(chat_id, current_user['email'])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    return await message_repository.get_chat_messages(chat_id, current_user['email'])

@router.post("/{chat_id}/messages")
async def create_message(
    chat_id: str,
    message: ChatMessageCreate,
    current_user: dict = Depends(get_current_user),
    rag_service: RAGService = Depends(lambda: RAGService())
):
    try:
        # Get chat details
        chat = await chat_repository.get_chat(chat_id, current_user['email'])
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
            
        # Get chat history
        chat_history = await message_repository.get_chat_messages(chat_id, current_user['email'])
            
        # Save user message
        user_message = await message_repository.create_message(
            chat_id=chat_id,
            content=message.content,
            role="user",
            user_id=current_user['email']
        )
        
        # Update chat's last_modified timestamp
        await chat_repository.update_last_modified(chat_id, current_user['email'])
        
        # Get enabled documents for the knowledge bases
        enabled_documents = await document_repository.get_enabled_documents_for_knowledge_bases(
            knowledge_base_ids=chat['knowledge_base_ids'],
            user_id=current_user['email']
        )
        document_ids = [doc['id'] for doc in enabled_documents]
        
        # Get relevant chunks using RAG
        relevant_chunks = await rag_service.get_relevant_chunks(
            query=message.content,
            knowledge_base_ids=chat['knowledge_base_ids'],
            enabled_document_ids=document_ids,
            user_id=current_user['email']
        )
        
        # Generate response using chat history
        ai_response = await rag_service.generate_response(
            query=message.content,
            contexts=relevant_chunks,
            chat_history=chat_history
        )
        
        # Save AI response
        assistant_message = await message_repository.create_message(
            chat_id=chat_id,
            content=ai_response,
            role="assistant",
            user_id=current_user['email']
        )
        
        return {
            "user_message": user_message,
            "assistant_message": assistant_message
        }
        
    except Exception as e:
        logger.error(f"Error in create_message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        ) 