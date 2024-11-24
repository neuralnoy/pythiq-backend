from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from ....schemas.parsed_document import ParsedDocument
from ....db.repositories.parsed_documents import parsed_document_repository
from ....auth.deps import get_current_user
from ....core.config import settings

router = APIRouter()

@router.get("/{knowledge_base_id}/{document_id}/parsed", response_model=List[ParsedDocument])
async def get_parsed_documents(
    knowledge_base_id: str,
    document_id: str,
    current_user = Depends(get_current_user)
):
    """Get all parsed versions of a document"""
    try:
        parsed_docs = await parsed_document_repository.get_parsed_documents(
            document_id,
            knowledge_base_id,
            current_user['email']
        )
        return parsed_docs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/{knowledge_base_id}/{document_id}/parsed/{parsed_id}/content")
async def get_parsed_content(
    knowledge_base_id: str,
    document_id: str,
    parsed_id: str,
    current_user = Depends(get_current_user)
):
    """Get the parsed content of a specific version"""
    try:
        content = await parsed_document_repository.get_parsed_content(
            parsed_id,
            document_id,
            knowledge_base_id,
            current_user['email']
        )
        return {"content": content}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
