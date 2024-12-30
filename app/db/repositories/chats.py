from typing import List, Dict, Optional
from datetime import datetime
import uuid
from ...db.client import chats_table
from boto3.dynamodb.conditions import Key

class ChatRepository:
    async def create(self, data: Dict) -> Dict:
        current_time = datetime.utcnow().isoformat() + 'Z'
        chat = {
            'id': str(uuid.uuid4()),
            'title': data['title'],
            'knowledge_base_ids': data['knowledge_base_ids'],
            'user_id': data['user_id'],
            'created_at': current_time,
            'last_modified': current_time,
            'token_count': 0
        }
        
        chats_table.put_item(Item=chat)
        return chat

    async def get_by_user(self, user_id: str) -> List[Dict]:
        try:
            response = chats_table.query(
                IndexName='user_id-last_modified-index',
                KeyConditionExpression=Key('user_id').eq(user_id),
                ScanIndexForward=False  # This will sort by last_modified in descending order
            )
            return response.get('Items', [])
        except Exception as e:
            print(f"Error querying chats: {str(e)}")
            return []

    async def delete(self, chat_id: str, user_id: str) -> bool:
        try:
            response = chats_table.delete_item(
                Key={'id': chat_id},
                ConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id}
            )
            return True
        except Exception as e:
            print(f"Error deleting chat: {str(e)}")
            return False

    async def get_chat(self, chat_id: str, user_id: str) -> Optional[Dict]:
        try:
            response = chats_table.get_item(
                Key={'id': chat_id}
            )
            item = response.get('Item')
            if item and item['user_id'] == user_id:
                return item
            return None
        except Exception as e:
            print(f"Error getting chat: {str(e)}")
            return None

chat_repository = ChatRepository() 