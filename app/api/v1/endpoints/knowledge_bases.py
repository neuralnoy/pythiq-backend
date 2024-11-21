from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.knowledge_base import KnowledgeBase, KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.db.repositories.knowledge_bases import knowledge_base_repository
from app.auth.deps import get_current_user

router = APIRouter()

@router.get("/", response_model=List[KnowledgeBase])
async def get_knowledge_bases(current_user = Depends(get_current_user)):
    """Get all knowledge bases for the current user"""
    try:
        knowledge_bases = await knowledge_base_repository.get_by_user(current_user['email'])
        return knowledge_bases
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/", response_model=KnowledgeBase)
async def create_knowledge_base(
    knowledge_base: KnowledgeBaseCreate,
    current_user = Depends(get_current_user)
):
    """Create a new knowledge base"""
    # Check if title already exists for user
    existing = await knowledge_base_repository.get_by_title_and_user(
        knowledge_base.title,
        current_user['email']
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A knowledge base with this title already exists"
        )
    
    return await knowledge_base_repository.create({
        **knowledge_base.dict(),
        "user_id": current_user['email']
    })

@router.delete("/{knowledge_base_id}")
async def delete_knowledge_base(
    knowledge_base_id: str,
    current_user = Depends(get_current_user)
):
    """Delete a knowledge base"""
    success = await knowledge_base_repository.delete(knowledge_base_id, current_user['email'])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found or you don't have permission to delete it"
        )
    return {"message": "Knowledge base deleted successfully"}

@router.patch("/{knowledge_base_id}", response_model=KnowledgeBase)
async def update_knowledge_base(
    knowledge_base_id: str,
    knowledge_base: KnowledgeBaseUpdate,
    current_user = Depends(get_current_user)
):
    """Update a knowledge base"""
    existing_kb = await knowledge_base_repository.get_by_id_and_user(
        knowledge_base_id,
        current_user['email']
    )
    if not existing_kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found or you don't have permission to update it"
        )
    
    if existing_kb['title'] != knowledge_base.title:
        title_exists = await knowledge_base_repository.get_by_title_and_user(
            knowledge_base.title,
            current_user['email']
        )
        if title_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A knowledge base with this title already exists"
            )
    
    updated_kb = await knowledge_base_repository.update(
        knowledge_base_id,
        current_user['email'],
        knowledge_base.dict()
    )
    
    if not updated_kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Failed to update knowledge base"
        )
    
    return updated_kb 