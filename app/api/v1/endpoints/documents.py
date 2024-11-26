from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from typing import List
from app.schemas.document import Document, DocumentUploadResponse
from app.db.repositories.documents import document_repository
from app.auth.deps import get_current_user
from app.db.repositories.knowledge_bases import knowledge_base_repository
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.db.client import s3_client
import io
from app.utils.file_types import is_valid_file_type
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

class RenameRequest(BaseModel):
    name: str

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
    file: UploadFile = File(...),
    current_user = Depends(get_current_user)
):
    try:
        if not file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )
        
        # Log file details for debugging
        logger.info(f"Uploading file: {file.filename}, content_type: {file.content_type}")
            
        # Check file size
        file_content = await file.read()
        file_size = len(file_content)
        await file.seek(0)  # Reset file pointer
        
        if file_size > 100 * 1024 * 1024:  # 100MB limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size too large. Maximum size is 100MB"
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

        try:
            document = await document_repository.upload_document(
                file,
                knowledge_base_id,
                current_user['email']
            )
            return document
        except Exception as upload_error:
            logger.error(f"Upload error: {str(upload_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file: {str(upload_error)}"
            )
            
    except Exception as e:
        logger.error(f"Unexpected error during upload: {str(e)}")
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

@router.patch("/{knowledge_base_id}/{document_id}/rename", response_model=Document)
async def rename_document(
    knowledge_base_id: str,
    document_id: str,
    rename_request: RenameRequest,
    current_user = Depends(get_current_user)
):
    try:
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

        # Rename the document
        document = await document_repository.rename_document(
            knowledge_base_id,
            document_id,
            rename_request.name,
            current_user['email']
        )
        return document
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

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

@router.get("/{knowledge_base_id}/{document_id}", response_model=Document)
async def get_document(
    knowledge_base_id: str,
    document_id: str,
    current_user = Depends(get_current_user)
):
    try:
        document = await document_repository.get_document(document_id, current_user['email'])
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        return document
    except Exception as e:
        logger.error(f"Error getting document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        ) 