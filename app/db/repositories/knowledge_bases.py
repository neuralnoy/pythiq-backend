from typing import List, Dict, Optional
from uuid import uuid4
from datetime import datetime, timezone
from ..client import knowledge_bases_table

class KnowledgeBaseRepository:
    async def get_all_by_user(self, user_id: str) -> List[Dict]:
        response = knowledge_bases_table.query(
            IndexName='user_id-index',
            KeyConditionExpression='user_id = :user_id',
            ExpressionAttributeValues={
                ':user_id': user_id
            }
        )
        return response.get('Items', [])

    async def create(self, knowledge_base_data: Dict) -> Dict:
        knowledge_base_data['id'] = str(uuid4())
        knowledge_base_data['created_at'] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        knowledge_bases_table.put_item(Item=knowledge_base_data)
        return knowledge_base_data

    async def delete(self, id: str, user_id: str) -> bool:
        try:
            knowledge_bases_table.delete_item(
                Key={'id': id},
                ConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id}
            )
            return True
        except Exception:
            return False

    async def get_by_title_and_user(self, title: str, user_id: str) -> Optional[Dict]:
        response = knowledge_bases_table.scan(
            FilterExpression='title = :title AND user_id = :user_id',
            ExpressionAttributeValues={
                ':title': title,
                ':user_id': user_id
            }
        )
        items = response.get('Items', [])
        return items[0] if items else None

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
        except Exception:
            return None

    async def get_by_id_and_user(self, id: str, user_id: str) -> Optional[Dict]:
        response = knowledge_bases_table.get_item(
            Key={'id': id}
        )
        item = response.get('Item')
        if item and item['user_id'] == user_id:
            return item
        return None

knowledge_base_repository = KnowledgeBaseRepository() 