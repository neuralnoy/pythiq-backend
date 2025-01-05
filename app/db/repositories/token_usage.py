from typing import Dict, List, Optional
from datetime import datetime
import uuid
from ..client import token_usage_table
from boto3.dynamodb.conditions import Key

class TokenUsageRepository:
    async def create_usage_record(
        self,
        user_id: str,
        chat_id: str,
        completion_tokens: int,
        prompt_tokens: int,
        embedding_tokens: int = 0,
        operation_type: str = "chat"  # can be "chat" or "embedding"
    ) -> Dict:
        current_time = datetime.utcnow().isoformat()
        usage_record = {
            'id': str(uuid.uuid4()),
            'user_id': user_id,
            'chat_id': chat_id,
            'completion_tokens': completion_tokens,
            'prompt_tokens': prompt_tokens,
            'embedding_tokens': embedding_tokens,
            'operation_type': operation_type,
            'created_at': current_time,
            'date': current_time.split('T')[0]  # For querying by date
        }
        
        token_usage_table.put_item(Item=usage_record)
        return usage_record

    async def get_usage_by_user_and_date_range(
        self,
        user_id: str,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        try:
            response = token_usage_table.query(
                IndexName='user_id-date-index',
                KeyConditionExpression=Key('user_id').eq(user_id) & 
                                     Key('date').between(start_date, end_date)
            )
            return response.get('Items', [])
        except Exception as e:
            print(f"Error querying token usage: {str(e)}")
            return []

    async def get_usage_by_chat(
        self,
        chat_id: str,
        user_id: str
    ) -> List[Dict]:
        try:
            response = token_usage_table.query(
                IndexName='chat_id-created_at-index',
                KeyConditionExpression=Key('chat_id').eq(chat_id),
                FilterExpression='user_id = :uid',
                ExpressionAttributeValues={
                    ':uid': user_id
                }
            )
            return response.get('Items', [])
        except Exception as e:
            print(f"Error querying chat token usage: {str(e)}")
            return []

token_usage_repository = TokenUsageRepository() 