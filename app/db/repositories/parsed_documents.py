from typing import Dict, Optional, List
from uuid import uuid4
from datetime import datetime, timezone
from ..client import s3_client, parsed_documents_table, documents_table
from ...core.config import settings
from docling.document_converter import DocumentConverter, DocumentStream
from pathlib import Path
import tempfile
import logging

logger = logging.getLogger(__name__)

class ParsedDocumentRepository:
    def __init__(self):
        self.converter = DocumentConverter()
    
    async def parse_document(self, document: Dict) -> Dict:
        try:
            parsed_id = str(uuid4())
            original_path = document['path']
            parsed_path = f"{document['user_id']}/{document['knowledge_base_id']}/{document['id']}/parsed/{parsed_id}.md"
            
            logger.info(f"Starting parsing for document {document['id']}")
            
            # Create initial metadata record
            parsed_metadata = {
                'id': parsed_id,
                'document_id': document['id'],
                'knowledge_base_id': document['knowledge_base_id'],
                'user_id': document['user_id'],
                'original_path': original_path,
                'parsed_path': parsed_path,
                'parse_status': 'processing',
                'parsed_at': datetime.now(timezone.utc).isoformat(),
            }
            
            try:
                # Get file from S3 and process
                s3_response = s3_client.get_object(
                    Bucket=settings.AWS_BUCKET_NAME,
                    Key=original_path
                )
                
                with tempfile.NamedTemporaryFile(suffix=Path(document['name']).suffix, delete=False) as temp_file:
                    temp_file.write(s3_response['Body'].read())
                    temp_file.flush()
                    result = self.converter.convert(Path(temp_file.name))
                    markdown_content = result.document.export_to_markdown()
                
                # Upload parsed content to S3
                s3_client.put_object(
                    Bucket=settings.AWS_BUCKET_NAME,
                    Key=parsed_path,
                    Body=markdown_content.encode('utf-8'),
                    ContentType='text/markdown'
                )
                
                logger.info(f"Successfully parsed document {document['id']}, updating status to done")
                
                # Update parsed document status
                parsed_metadata['parse_status'] = 'done'
                parsed_documents_table.put_item(Item=parsed_metadata)
                
                # Get the current document to preserve all attributes
                current_doc = documents_table.get_item(
                    Key={'id': document['id']}
                ).get('Item', {})
                
                # Update the document with all its current attributes plus the new status
                current_doc.update({
                    'parsing_status': 'done',
                    'updated_at': datetime.now(timezone.utc).isoformat()
                })
                
                logger.info(f"Updating document table for {document['id']} with status: done")
                documents_table.put_item(Item=current_doc)
                
                return parsed_metadata
                
            except Exception as e:
                logger.error(f"Error during parsing: {str(e)}")
                
                # Update parsed document status
                parsed_metadata['parse_status'] = 'failed'
                parsed_metadata['error_message'] = str(e)
                parsed_documents_table.put_item(Item=parsed_metadata)
                
                # Update document status
                current_doc = documents_table.get_item(
                    Key={'id': document['id']}
                ).get('Item', {})
                
                current_doc.update({
                    'parsing_status': 'failed',
                    'updated_at': datetime.now(timezone.utc).isoformat()
                })
                
                documents_table.put_item(Item=current_doc)
                
                raise
                
        except Exception as e:
            logger.error(f"Error in parse_document: {str(e)}")
            raise

    async def get_parsed_documents(
        self,
        document_id: str,
        knowledge_base_id: str,
        user_id: str
    ) -> List[Dict]:
        """Get all parsed versions of a document"""
        try:
            response = parsed_documents_table.query(
                KeyConditionExpression='document_id = :did',
                FilterExpression='user_id = :uid AND knowledge_base_id = :kid',
                ExpressionAttributeValues={
                    ':did': document_id,
                    ':uid': user_id,
                    ':kid': knowledge_base_id
                }
            )
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"Error fetching parsed documents: {str(e)}")
            raise

    async def get_parsed_content(
        self,
        parsed_id: str,
        document_id: str,
        knowledge_base_id: str,
        user_id: str
    ) -> str:
        """Get the content of a specific parsed version"""
        try:
            # Get metadata to verify access and get path
            response = parsed_documents_table.get_item(
                Key={'id': parsed_id}
            )
            metadata = response.get('Item')
            
            if not metadata or metadata['user_id'] != user_id:
                raise Exception("Parsed document not found or access denied")
            
            # Get content from S3
            s3_response = s3_client.get_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=metadata['parsed_path']
            )
            
            return s3_response['Body'].read().decode('utf-8')
        except Exception as e:
            logger.error(f"Error fetching parsed content: {str(e)}")
            raise

# Initialize the repository
parsed_document_repository = ParsedDocumentRepository()
