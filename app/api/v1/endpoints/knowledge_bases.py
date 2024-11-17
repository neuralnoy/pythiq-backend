from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from ....schemas.knowledge_base import KnowledgeBase, KnowledgeBaseCreate
from ....db.repositories.knowledge_bases import knowledge_base_repository
from ....auth.deps import get_current_user

router = APIRouter()

@router.get("/", response_model=List[KnowledgeBase])
async def get_knowledge_bases(current_user = Depends(get_current_user)):
    """Get all knowledge bases for the current user"""
    return await knowledge_base_repository.get_all_by_user(current_user['email'])

@router.post("/", response_model=KnowledgeBase)
async def create_knowledge_base(
    knowledge_base: KnowledgeBaseCreate,
    current_user = Depends(get_current_user)
):
    """Create a new knowledge base"""
    # Check if knowledge base with same title exists for user
    existing_kb = await knowledge_base_repository.get_by_title_and_user(
        knowledge_base.title,
        current_user['email']
    )
    if existing_kb:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A knowledge base with this title already exists"
        )

    knowledge_base_data = {
        "title": knowledge_base.title,
        "user_id": current_user['email']
    }
    
    return await knowledge_base_repository.create(knowledge_base_data)

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