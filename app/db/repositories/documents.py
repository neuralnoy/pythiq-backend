from typing import List, Dict, Optional
from uuid import uuid4
from datetime import datetime, timezone
from ..client import s3_client, documents_table, parsed_documents_table
from ...core.config import settings
import asyncio
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import ClientError
import backoff
import logging
from boto3.dynamodb.conditions import Key
from pymilvus import MilvusClient

logger = logging.getLogger(__name__)

class DocumentRepository:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5)  # Limit concurrent uploads
        self.milvus_client = MilvusClient(
            uri=settings.ZILLIZ_CLOUD_URI,
            token=settings.ZILLIZ_CLOUD_API_KEY
        )

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
            await self._upload_to_s3(
                file.file,
                settings.AWS_BUCKET_NAME,
                s3_path,
                content_type
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
            
            # Return metadata immediately - parsing will happen in background
            return document_metadata
            
        except Exception as e:
            logger.error(f"Document upload error: {str(e)}")
            raise

    def _guess_content_type(self, filename: str) -> str:
        """Guess the content type based on file extension"""
        extension = filename.lower().split('.')[-1]
        content_types = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'png': 'image/png'
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
            # First get the document to verify ownership and get the path
            response = documents_table.get_item(
                Key={'id': document_id}
            )
            document = response.get('Item')
            
            if not document or document['user_id'] != user_id:
                return False

            # Delete all related objects from S3
            # 1. Main document folder
            main_prefix = f"{user_id}/{knowledge_base_id}/{document_id}/"
            # 2. Processed folder
            processed_prefix = f"{user_id}/{knowledge_base_id}/{document_id}/processed/"
            
            # List and delete all objects with these prefixes
            for prefix in [main_prefix, processed_prefix]:
                response = s3_client.list_objects_v2(
                    Bucket=settings.AWS_BUCKET_NAME,
                    Prefix=prefix
                )
                
                if 'Contents' in response:
                    for obj in response['Contents']:
                        s3_client.delete_object(
                            Bucket=settings.AWS_BUCKET_NAME,
                            Key=obj['Key']
                        )
                        logger.info(f"Deleted S3 object: {obj['Key']}")

            # Delete from Zilliz/Milvus
            try:
                # Sanitize collection name (same as in RAGService)
                collection_name = user_id.replace('.', '_').replace('@', '_')
                while '__' in collection_name:
                    collection_name = collection_name.replace('__', '_')
                collection_name = collection_name.rstrip('_')

                # Delete all entries for this document
                delete_expr = f"document_id == '{document_id}'"
                self.milvus_client.delete(
                    collection_name=collection_name,
                    filter=delete_expr
                )
                logger.info(f"Deleted entries from Milvus for document: {document_id}")
            except Exception as e:
                logger.error(f"Error deleting from Milvus: {str(e)}")
                # Continue with deletion of other resources even if Milvus deletion fails

            # Delete from parsed_documents table using id (not document_id)
            try:
                parsed_documents_table.delete_item(
                    Key={
                        'id': document_id
                    }
                )
                logger.info(f"Deleted record from parsed_documents table: {document_id}")
            except Exception as e:
                logger.error(f"Error deleting from parsed_documents table: {str(e)}")

            # Delete from documents table
            documents_table.delete_item(
                Key={'id': document_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            return False

    async def generate_download_url(self, document_id: str, knowledge_base_id: str, user_id: str) -> Optional[str]:
        try:
            # Get document metadata to get the original file path
            response = documents_table.get_item(
                Key={'id': document_id}
            )
            document = response.get('Item')
            
            if not document or document['user_id'] != user_id:
                return None

            # Get the original file path from the document metadata
            original_path = document['path']
            
            # Generate presigned URL for the original file
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.AWS_BUCKET_NAME,
                    'Key': original_path
                },
                ExpiresIn=3600  # URL expires in 1 hour
            )
            return url
        except Exception as e:
            logger.error(f"Error generating download URL: {str(e)}")
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
            logger.info(f"""
            Fetching document with parameters:
            - Document ID: {document_id}
            - User ID: {user_id}
            """)
            
            # First, let's see what's in the table
            scan_response = documents_table.scan(
                FilterExpression='id = :id',
                ExpressionAttributeValues={
                    ':id': document_id
                }
            )
            logger.info(f"Scan results: {scan_response.get('Items', [])}")
            
            # Now try the get_item
            response = documents_table.get_item(
                Key={'id': document_id}
            )
            
            document = response.get('Item')
            logger.info(f"Get_item result: {document}")
            
            if not document:
                logger.warning(f"Document not found with ID: {document_id}")
                return None
                
            if document['user_id'] != user_id:
                logger.warning(f"""
                User ID mismatch:
                - Document user_id: {document['user_id']}
                - Requesting user_id: {user_id}
                """)
                return None
                
            return document
            
        except Exception as e:
            logger.exception(f"Error fetching document: {str(e)}")
            raise Exception(f"Failed to fetch document: {str(e)}")

    async def get_enabled_documents_for_knowledge_bases(
        self,
        knowledge_base_ids: List[str],
        user_id: str
    ) -> List[Dict]:
        try:
            enabled_documents = []
            for kb_id in knowledge_base_ids:
                response = documents_table.query(
                    IndexName='knowledge_base_id-index',
                    KeyConditionExpression=Key('knowledge_base_id').eq(kb_id),
                    FilterExpression='user_id = :uid AND enabled = :enabled',
                    ExpressionAttributeValues={
                        ':uid': user_id,
                        ':enabled': True
                    }
                )
                enabled_documents.extend(response.get('Items', []))
            return enabled_documents
        except Exception as e:
            print(f"Error getting enabled documents: {str(e)}")
            return []

document_repository = DocumentRepository()