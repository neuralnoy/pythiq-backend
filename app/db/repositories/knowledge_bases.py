from typing import List, Dict, Optional
from boto3.dynamodb.conditions import Key
from app.db.client import knowledge_bases_table, documents_table, s3_client
from datetime import datetime
import uuid
import boto3
from app.core.config import settings
import logging

# Add logger
logger = logging.getLogger(__name__)

class KnowledgeBaseRepository:
    async def create(self, data: Dict) -> Dict:
        knowledge_base = {
            'id': str(uuid.uuid4()),
            'title': data['title'],
            'user_id': data['user_id'],
            'created_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        knowledge_bases_table.put_item(Item=knowledge_base)
        return knowledge_base

    async def get_by_user(self, user_id: str) -> List[Dict]:
        try:
            # Get knowledge bases
            response = knowledge_bases_table.query(
                IndexName='user_id-index',
                KeyConditionExpression=Key('user_id').eq(user_id)
            )
            knowledge_bases = response.get('Items', [])
            
            # Get document counts for each knowledge base
            for kb in knowledge_bases:
                doc_response = documents_table.query(
                    IndexName='knowledge_base_id-index',
                    KeyConditionExpression=Key('knowledge_base_id').eq(kb['id']),
                    FilterExpression='user_id = :uid',
                    ExpressionAttributeValues={
                        ':uid': user_id
                    }
                )
                kb['document_count'] = len(doc_response.get('Items', []))
            
            return knowledge_bases
        except Exception as e:
            print(f"Error querying knowledge bases: {str(e)}")
            return []

    async def get_by_title_and_user(self, title: str, user_id: str) -> Optional[Dict]:
        try:
            # First get all knowledge bases for the user
            response = knowledge_bases_table.query(
                IndexName='user_id-index',
                KeyConditionExpression=Key('user_id').eq(user_id)
            )
            
            # Then filter by title
            items = response.get('Items', [])
            for item in items:
                if item['title'].lower() == title.lower():
                    return item
            return None
        except Exception as e:
            print(f"Error checking title existence: {str(e)}")
            return None

    async def delete(self, id: str, user_id: str) -> bool:
        try:
            # First verify the knowledge base belongs to the user
            response = knowledge_bases_table.get_item(
                Key={'id': id}
            )
            
            item = response.get('Item')
            if not item or item['user_id'] != user_id:
                return False
            
            # Get all documents for this knowledge base
            doc_response = documents_table.query(
                IndexName='knowledge_base_id-index',
                KeyConditionExpression=Key('knowledge_base_id').eq(id),
                FilterExpression='user_id = :uid',
                ExpressionAttributeValues={
                    ':uid': user_id
                }
            )
            
            documents = doc_response.get('Items', [])
            
            # Delete all documents
            for document in documents:
                try:
                    # Delete original document from S3
                    s3_client = boto3.client('s3')
                    s3_client.delete_object(
                        Bucket=settings.AWS_BUCKET_NAME,
                        Key=document['path']
                    )
                    
                    # Delete document metadata
                    documents_table.delete_item(
                        Key={'id': document['id']}
                    )
                    
                except Exception as e:
                    logger.error(f"Error deleting document {document['id']}: {str(e)}")
            
            # Finally delete the knowledge base
            knowledge_bases_table.delete_item(
                Key={'id': id},
                ConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id}
            )
            return True
        
        except Exception as e:
            logger.error(f"Error in cascading delete of knowledge base: {str(e)}")
            return False

    async def update(self, id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
        try:
            response = knowledge_bases_table.update_item(
                Key={'id': id},
                UpdateExpression='SET title = :title',
                ConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={
                    ':title': update_data['title'],
                    ':user_id': user_id
                },
                ReturnValues='ALL_NEW'
            )
            return response.get('Attributes')
        except Exception as e:
            print(f"Error updating knowledge base: {str(e)}")
            return None

    async def get_by_id_and_user(self, id: str, user_id: str) -> Optional[Dict]:
        try:
            response = knowledge_bases_table.get_item(
                Key={'id': id}
            )
            item = response.get('Item')
            if item and item['user_id'] == user_id:
                return item
            return None
        except Exception as e:
            print(f"Error getting knowledge base: {str(e)}")
            return None

knowledge_base_repository = KnowledgeBaseRepository() 