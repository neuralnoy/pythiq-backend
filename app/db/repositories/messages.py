from typing import List, Dict, Optional
from datetime import datetime
import uuid
from ...db.client import dynamodb

messages_table = dynamodb.Table('messages')

class MessageRepository:
    async def create_message(
        self,
        chat_id: str,
        content: str,
        role: str,
        user_id: str
    ) -> Dict:
        message_id = str(uuid.uuid4())
        current_time = datetime.utcnow().isoformat() + 'Z'
        
        message = {
            'id': message_id,
            'chat_id': chat_id,
            'content': content,
            'role': role,
            'user_id': user_id,
            'created_at': current_time,
            'last_modified': current_time
        }
        
        messages_table.put_item(Item=message)
        return message

    async def get_chat_messages(self, chat_id: str, user_id: str) -> List[Dict]:
        try:
            from boto3.dynamodb.conditions import Key
            
            response = messages_table.query(
                IndexName='chat_id-created_at-index',
                KeyConditionExpression=Key('chat_id').eq(chat_id),
                FilterExpression='user_id = :uid',
                ExpressionAttributeValues={
                    ':uid': user_id
                }
            )
            return response.get('Items', [])
        except Exception as e:
            print(f"Error querying messages: {str(e)}")
            return []

    async def delete_by_chat_id(self, chat_id: str, user_id: str) -> bool:
        try:
            # First get all messages for this chat
            messages = await self.get_chat_messages(chat_id, user_id)
            
            # Delete each message
            with messages_table.batch_writer() as batch:
                for message in messages:
                    batch.delete_item(
                        Key={
                            'id': message['id']
                        }
                    )
            return True
        except Exception as e:
            print(f"Error deleting messages for chat {chat_id}: {str(e)}")
            return False

message_repository = MessageRepository() 