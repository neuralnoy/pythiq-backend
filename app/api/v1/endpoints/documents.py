from fastapi import APIRouter, UploadFile, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List
from ....schemas.document import Document
from ....db.repositories.documents import document_repository
from ....auth.deps import get_current_user, security
from ....db.repositories.knowledge_bases import knowledge_base_repository

router = APIRouter()

@router.get("/{knowledge_base_id}", response_model=List[Document])
async def get_documents(
    knowledge_base_id: str,
    current_user = Depends(get_current_user)
):
    try:
        print(f"Fetching documents for KB: {knowledge_base_id}, user: {current_user['email']}")
        documents = await document_repository.get_documents(
            knowledge_base_id,
            current_user['email']
        )
        print(f"Found {len(documents)} documents")
        return documents
    except Exception as e:
        print(f"Error in get_documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{knowledge_base_id}/upload", response_model=Document)
async def upload_document(
    knowledge_base_id: str,
    file: UploadFile,
    current_user = Depends(get_current_user)
):
    try:
        if not file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )
            
        # Optional: Add file size check
        file_size = 0
        file_content = await file.read()
        file_size = len(file_content)
        await file.seek(0)  # Reset file pointer
        
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size too large. Maximum size is 10MB"
            )

        # Check if knowledge base exists and belongs to user
        kb = await knowledge_base_repository.get_by_id_and_user(
            knowledge_base_id,
            current_user['email']
        )
        if not kb:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found or you don't have permission"
            )

        document = await document_repository.upload_document(
            file,
            knowledge_base_id,
            current_user['email']
        )
        return document
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        ) 