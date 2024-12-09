from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, BackgroundTasks
from typing import List, Dict
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
from app.services.parser_service import parser_service

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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
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
        
        if file_size > 20 * 1024 * 1024:  # 20MB limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size too large. Maximum size is 20MB"
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

            async def parse_with_error_handling(doc):
                try:
                    await parser_service.start_parsing(doc)
                    await document_repository.update_parsing_status(
                        knowledge_base_id,
                        doc['id'],
                        'done',
                        current_user['email']
                    )
                except Exception as e:
                    logger.error(f"Parsing failed: {str(e)}")
                    await document_repository.update_parsing_status(
                        knowledge_base_id,
                        doc['id'],
                        'failed',
                        current_user['email']
                    )

            background_tasks.add_task(parse_with_error_handling, document)
            
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

@router.get("/{knowledge_base_id}/{document_id}/download")
async def download_document(
    knowledge_base_id: str,
    document_id: str,
    current_user = Depends(get_current_user)
):
    try:
        # Get document metadata to get the original file path
        document = await document_repository.get_document(document_id, current_user['email'])
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Use the original file path from document metadata
        file_key = document['path']
        
        try:
            file_obj = s3_client.get_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=file_key
            )
        except s3_client.exceptions.NoSuchKey:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found in storage"
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download document"
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

@router.post("/{knowledge_base_id}/{document_id}/parse", status_code=status.HTTP_202_ACCEPTED)
async def start_parsing(
    knowledge_base_id: str,
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
) -> Dict:
    """Start or restart document parsing"""
    try:
        # Debug print to see the full current_user object
        logger.info(f"Current user object: {current_user}")
        
        user_id = current_user.get('email')  # Change from user_id to email since that's what we're using
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )

        logger.info(f"""
        Attempting to parse document:
        - Knowledge Base ID: {knowledge_base_id}
        - Document ID: {document_id}
        - User ID: {user_id}
        """)
        
        # Get document metadata
        document = await document_repository.get_document(document_id, user_id)
        
        if not document:
            logger.error(f"Document not found: {document_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
            
        if document['knowledge_base_id'] != knowledge_base_id:
            logger.error(f"Document {document_id} does not belong to knowledge base {knowledge_base_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document does not belong to this knowledge base"
            )
        
        logger.info(f"Document found: {document}")
        
        # Add parsing task to background tasks
        background_tasks.add_task(
            parser_service.start_parsing,
            document
        )
        
        # Update status to processing - use email as user_id
        updated_doc = await document_repository.update_parsing_status(
            knowledge_base_id,
            document_id,
            'processing',
            user_id
        )
        
        return {
            "status": "processing",
            "document": updated_doc
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error starting parsing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/{knowledge_base_id}/{document_id}/parse-status")
async def get_parsing_status(
    knowledge_base_id: str,
    document_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict:
    """Get document parsing status"""
    try:
        user_id = current_user.get('email')  # Change from id to email
        document = await document_repository.get_document(document_id, user_id)
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
            
        if document['knowledge_base_id'] != knowledge_base_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document does not belong to this knowledge base"
            )
            
        return {
            "status": document.get('parsing_status', 'unknown'),
            "document_id": document_id
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        ) 

@router.patch("/{knowledge_base_id}/{document_id}/toggle", response_model=Document)
async def toggle_document(
    knowledge_base_id: str,
    document_id: str,
    current_user = Depends(get_current_user)
):
    try:
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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        ) 