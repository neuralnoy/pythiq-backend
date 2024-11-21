from fastapi import APIRouter, UploadFile, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List
from app.schemas.document import Document
from app.db.repositories.documents import document_repository
from app.auth.deps import get_current_user, security
from app.db.repositories.knowledge_bases import knowledge_base_repository
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.db.client import s3_client
import io

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

@router.delete("/{knowledge_base_id}/{document_id}")
async def delete_document(
    knowledge_base_id: str,
    document_id: str,
    current_user = Depends(get_current_user)
):
    success = await document_repository.delete_document(
        document_id,
        knowledge_base_id,
        current_user['email']
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you don't have permission"
        )
    return {"message": "Document deleted successfully"}

@router.patch("/{knowledge_base_id}/{document_id}")
async def rename_document(
    knowledge_base_id: str,
    document_id: str,
    update_data: dict,
    current_user = Depends(get_current_user)
):
    document = await document_repository.rename_document(
        document_id,
        knowledge_base_id,
        current_user['email'],
        update_data['name']
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you don't have permission"
        )
    return document

@router.get("/{knowledge_base_id}/{document_id}/download")
async def download_document(
    knowledge_base_id: str,
    document_id: str,
    current_user = Depends(get_current_user)
):
    try:
        response = s3_client.list_objects_v2(
            Bucket=settings.AWS_BUCKET_NAME,
            Prefix=f"{current_user['email']}/{knowledge_base_id}/{document_id}/"
        )
        
        if 'Contents' not in response or not response['Contents']:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        file_key = response['Contents'][0]['Key']
        file_obj = s3_client.get_object(
            Bucket=settings.AWS_BUCKET_NAME,
            Key=file_key
        )
        
        filename = file_key.split('/')[-1]
        content_type = file_obj.get('ContentType', 'application/octet-stream')
        
        return StreamingResponse(
            io.BytesIO(file_obj['Body'].read()),
            media_type=content_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': content_type
            }
        )
    except Exception as e:
        print(f"Download error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you don't have permission"
        )

@router.post("/{knowledge_base_id}/{document_id}/toggle")
async def toggle_document(
    knowledge_base_id: str,
    document_id: str,
    current_user = Depends(get_current_user)
):
    document = await document_repository.toggle_document_enabled(
        document_id,
        knowledge_base_id,
        current_user['email']
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you don't have permission"
        )
    return document 