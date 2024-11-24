from typing import List, Dict, Optional
from uuid import uuid4
from datetime import datetime, timezone
from ..client import s3_client, documents_table
from ...core.config import settings
import asyncio
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import ClientError
import backoff
import logging
from boto3.dynamodb.conditions import Key

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
            
            # Upload file to S3
            s3_path = f"{user_id}/{knowledge_base_id}/{file_id}/{filename}"
            s3_client.upload_fileobj(
                file.file,
                settings.AWS_BUCKET_NAME,
                s3_path,
                ExtraArgs={
                    'ContentType': content_type,
                    'ContentDisposition': f'inline; filename="{filename}"'
                }
            )
            
            # Store metadata in DynamoDB
            document_metadata = {
                'id': file_id,
                'name': filename,
                'type': content_type,
                'size': file.size,
                'knowledge_base_id': knowledge_base_id,
                'user_id': user_id,
                'path': s3_path,
                'uploaded_at': datetime.now(timezone.utc).isoformat(),
                'enabled': True,
                'parsing_status': 'processing'
            }
            
            documents_table.put_item(Item=document_metadata)
            
            # Trigger document parsing
            try:
                parsed_doc = await parsed_document_repository.parse_document(document_metadata)
                if parsed_doc:
                    # Update document status on successful parse
                    document_metadata['parsing_status'] = 'done'
                    documents_table.put_item(Item=document_metadata)
            except Exception as parse_error:
                logger.error(f"Parsing error: {str(parse_error)}")
                document_metadata['parsing_status'] = 'failed'
                documents_table.put_item(Item=document_metadata)
            
            return document_metadata
            
        except Exception as e:
            logger.error(f"Document upload error: {str(e)}")
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
            response = documents_table.query(
                IndexName='knowledge_base_id-index',
                KeyConditionExpression=Key('knowledge_base_id').eq(knowledge_base_id),
                FilterExpression=Key('user_id').eq(user_id)
            )
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"Error fetching documents: {str(e)}")
            return []

    async def delete_document(self, document_id: str, knowledge_base_id: str, user_id: str) -> bool:
        try:
            # Get document metadata
            response = documents_table.get_item(
                Key={'id': document_id}
            )
            document = response.get('Item')
            
            if not document or document['user_id'] != user_id:
                return False
                
            # Delete from S3
            s3_client.delete_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=document['path']
            )
            
            # Delete from DynamoDB
            documents_table.delete_item(
                Key={'id': document_id}
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
            # Get current document metadata from DynamoDB
            response = documents_table.get_item(
                Key={'id': document_id}
            )
            current_doc = response.get('Item')
            
            if not current_doc or current_doc['user_id'] != user_id:
                raise Exception("Document not found")

            # Create the new S3 key
            old_key = current_doc['path']
            new_key = f"{user_id}/{knowledge_base_id}/{document_id}/{new_name}"

            # Copy the object in S3 with new name
            s3_client.copy_object(
                Bucket=settings.AWS_BUCKET_NAME,
                CopySource={'Bucket': settings.AWS_BUCKET_NAME, 'Key': old_key},
                Key=new_key,
                ContentType=current_doc['type'],
                MetadataDirective='COPY'
            )

            # Delete old S3 object
            s3_client.delete_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=old_key
            )

            # Update DynamoDB metadata
            updated_doc = {
                **current_doc,
                'name': new_name,
                'path': new_key
            }
            documents_table.put_item(Item=updated_doc)

            return updated_doc

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
        try:
            # Get current document metadata
            response = documents_table.get_item(
                Key={'id': document_id}
            )
            document = response.get('Item')
            
            if not document or document['user_id'] != user_id:
                raise Exception("Document not found")

            # Update parsing status in DynamoDB
            updated_doc = {
                **document,
                'parsing_status': status
            }
            documents_table.put_item(Item=updated_doc)
            
            return updated_doc
        except Exception as e:
            logger.error(f"Error updating parsing status: {str(e)}")
            raise Exception(f"Failed to update parsing status: {str(e)}")

    async def toggle_document_enabled(self, document_id: str, knowledge_base_id: str, user_id: str) -> Optional[Dict]:
        try:
            # Get current document metadata
            response = documents_table.get_item(
                Key={'id': document_id}
            )
            document = response.get('Item')
            
            if not document or document['user_id'] != user_id:
                return None

            # Update enabled status in DynamoDB
            updated_doc = {
                **document,
                'enabled': not document.get('enabled', True)
            }
            documents_table.put_item(Item=updated_doc)
            
            return updated_doc
        except Exception as e:
            logger.error(f"Error toggling document: {str(e)}")
            return None

    async def get_document(self, document_id: str, user_id: str) -> Optional[Dict]:
        """
        Get a single document by ID and verify user has access to it
        """
        try:
            response = documents_table.get_item(
                Key={'id': document_id}
            )
            
            document = response.get('Item')
            
            # Verify document exists and belongs to user
            if not document or document['user_id'] != user_id:
                return None
                
            return document
            
        except Exception as e:
            logger.error(f"Error fetching document: {str(e)}")
            raise Exception(f"Failed to fetch document: {str(e)}")

document_repository = DocumentRepository()