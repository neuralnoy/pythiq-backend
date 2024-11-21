from typing import List, Dict, Optional
from uuid import uuid4
from datetime import datetime, timezone
from ..client import s3_client
from ...core.config import settings
import asyncio
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import ClientError
import backoff
import logging

logger = logging.getLogger(__name__)

class DocumentRepository:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5)  # Limit concurrent uploads

    @backoff.on_exception(
        backoff.expo,
        ClientError,
        max_tries=3,
        max_time=30
    )
    async def _upload_to_s3(self, file_obj, bucket: str, key: str, content_type: str):
        try:
            s3_client.upload_fileobj(
                file_obj,
                bucket,
                key,
                ExtraArgs={'ContentType': content_type}
            )
        except ClientError as e:
            print(f"S3 upload error: {str(e)}")
            raise

    async def upload_document(self, file, knowledge_base_id: str, user_id: str) -> Dict:
        try:
            file_id = str(uuid4())
            filename = file.filename
            content_type = file.content_type or self._guess_content_type(filename)
            
            logger.info(f"Preparing to upload: {filename} ({content_type})")
            
            # Ensure the content type is set for RTF files
            if filename.lower().endswith('.rtf'):
                content_type = 'application/rtf'
            
            try:
                s3_client.upload_fileobj(
                    file.file,
                    settings.AWS_BUCKET_NAME,
                    f"{user_id}/{knowledge_base_id}/{file_id}/{filename}",
                    ExtraArgs={
                        'ContentType': content_type,
                        'ContentDisposition': f'inline; filename="{filename}"'
                    }
                )
            except ClientError as e:
                logger.error(f"S3 upload error: {str(e)}")
                raise Exception(f"Failed to upload to S3: {str(e)}")
            
            return {
                "id": file_id,
                "name": filename,
                "type": content_type,
                "size": file.size,
                "knowledge_base_id": knowledge_base_id,
                "user_id": user_id,
                "path": f"{user_id}/{knowledge_base_id}/{file_id}/{filename}",
                "uploaded_at": datetime.now(timezone.utc),
                "enabled": True,
                "parsing_status": "pending"
            }
            
        except Exception as e:
            logger.error(f"Document repository error: {str(e)}")
            raise

    def _guess_content_type(self, filename: str) -> str:
        """Guess the content type based on file extension"""
        extension = filename.lower().split('.')[-1]
        content_types = {
            'rtf': 'application/rtf',
            'txt': 'text/plain',
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            # ... add other types as needed
        }
        return content_types.get(extension, 'application/octet-stream')

    async def get_documents(self, knowledge_base_id: str, user_id: str) -> List[Dict]:
        try:
            response = s3_client.list_objects_v2(
                Bucket=settings.AWS_BUCKET_NAME,
                Prefix=f"{user_id}/{knowledge_base_id}/"
            )
            
            if 'Contents' not in response:
                return []
                
            documents = []
            for obj in response['Contents']:
                # Skip if the object is a directory
                if obj['Key'].endswith('/'):
                    continue
                    
                documents.append({
                    "id": obj['Key'].split('/')[2],
                    "name": obj['Key'].split('/')[-1],
                    "size": obj['Size'],
                    "type": obj.get('ContentType', 'application/octet-stream'),
                    "knowledge_base_id": knowledge_base_id,
                    "user_id": user_id,
                    "path": obj['Key'],
                    "uploaded_at": obj['LastModified']
                })
            
            return documents
        except Exception as e:
            print(f"Error fetching documents: {str(e)}")
            return []

    async def delete_document(self, document_id: str, knowledge_base_id: str, user_id: str) -> bool:
        try:
            response = s3_client.list_objects_v2(
                Bucket=settings.AWS_BUCKET_NAME,
                Prefix=f"{user_id}/{knowledge_base_id}/{document_id}/"
            )
            
            for obj in response.get('Contents', []):
                s3_client.delete_object(
                    Bucket=settings.AWS_BUCKET_NAME,
                    Key=obj['Key']
                )
            return True
        except Exception:
            return False

    async def rename_document(
        self, 
        knowledge_base_id: str, 
        document_id: str, 
        new_name: str,
        user_id: str
    ) -> Dict:
        try:
            # Get the current document details
            documents = await self.get_documents(knowledge_base_id, user_id)
            current_doc = next((doc for doc in documents if doc['id'] == document_id), None)
            
            if not current_doc:
                raise Exception("Document not found")

            # Create the new key with the new name
            old_key = current_doc['path']
            new_key = f"{user_id}/{knowledge_base_id}/{document_id}/{new_name}"

            # Copy the object with the new name
            s3_client.copy_object(
                Bucket=settings.AWS_BUCKET_NAME,
                CopySource={'Bucket': settings.AWS_BUCKET_NAME, 'Key': old_key},
                Key=new_key,
                ContentType=current_doc['type'],
                MetadataDirective='COPY'
            )

            # Delete the old object
            s3_client.delete_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=old_key
            )

            # Return updated document info
            return {
                **current_doc,
                'name': new_name,
                'path': new_key
            }

        except Exception as e:
            logger.error(f"Error renaming document: {str(e)}")
            raise Exception(f"Failed to rename document: {str(e)}")

    async def generate_download_url(self, document_id: str, knowledge_base_id: str, user_id: str) -> Optional[str]:
        try:
            response = s3_client.list_objects_v2(
                Bucket=settings.AWS_BUCKET_NAME,
                Prefix=f"{user_id}/{knowledge_base_id}/{document_id}/"
            )
            
            if 'Contents' not in response:
                return None
                
            key = response['Contents'][0]['Key']
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.AWS_BUCKET_NAME,
                    'Key': key
                },
                ExpiresIn=3600  # URL expires in 1 hour
            )
            return url
        except Exception:
            return None

    async def update_parsing_status(
        self,
        knowledge_base_id: str,
        document_id: str,
        status: str,
        user_id: str
    ) -> Dict:
        # Implementation for updating parsing status
        # This would be called by your parsing service when processing is complete
        pass

document_repository = DocumentRepository()