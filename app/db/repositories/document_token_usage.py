from typing import Dict, List
from datetime import datetime
from ..client import dynamodb
from boto3.dynamodb.conditions import Key
import logging

logger = logging.getLogger(__name__)

class DocumentTokenUsageRepository:
    def __init__(self):
        self.embedding_tokens_table = dynamodb.Table('embedding_tokens')
        self.parser_token_usage_table = dynamodb.Table('parser_token_usage')

    async def get_usage_by_user_and_date_range(
        self,
        user_id: str,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        try:
            logger.info(f"Fetching document token usage for user {user_id} from {start_date} to {end_date}")
            
            # Get embedding tokens - using scan with filter since we don't have the right index
            embedding_response = self.embedding_tokens_table.scan(
                FilterExpression='user_id = :uid AND created_at BETWEEN :start AND :end',
                ExpressionAttributeValues={
                    ':uid': user_id,
                    ':start': start_date + 'T00:00:00',
                    ':end': end_date + 'T23:59:59'
                }
            )
            
            # Get parser tokens - using id and processed_at as composite key
            parser_response = self.parser_token_usage_table.query(
                KeyConditionExpression='id = :uid AND processed_at BETWEEN :start AND :end',
                ExpressionAttributeValues={
                    ':uid': user_id,
                    ':start': start_date + 'T00:00:00',
                    ':end': end_date + 'T23:59:59'
                }
            )
            
            # Process embedding tokens
            embedding_items = embedding_response.get('Items', [])
            parser_items = parser_response.get('Items', [])
            
            logger.info(f"Found {len(embedding_items)} embedding records and {len(parser_items)} parser records")
            
            if len(embedding_items) > 0:
                logger.info(f"Sample embedding record: {embedding_items[0]}")
            if len(parser_items) > 0:
                logger.info(f"Sample parser record: {parser_items[0]}")
            
            # Combine and format the data
            combined_data = {}
            
            # Process embedding tokens
            for item in embedding_items:
                # Keep full timestamp with timezone
                timestamp = item['created_at']
                logger.info(f"Embedding timestamp from DynamoDB: {timestamp}")
                if timestamp not in combined_data:
                    combined_data[timestamp] = {
                        'total_tokens': 0
                    }
                combined_data[timestamp]['total_tokens'] += item.get('total_tokens', 0)
            
            # Process parser tokens
            for item in parser_items:
                # Keep full timestamp with timezone
                timestamp = item['processed_at']
                logger.info(f"Parser timestamp from DynamoDB: {timestamp}")
                if timestamp not in combined_data:
                    combined_data[timestamp] = {
                        'total_tokens': 0
                    }
                # Add all tokens from image description
                input_tokens = item.get('input_tokens', {}).get('image_description', 0)
                output_tokens = item.get('output_tokens', {}).get('image_description', 0)
                
                combined_data[timestamp]['total_tokens'] += input_tokens + output_tokens
            
            # Convert to list format
            result = [
                {
                    'timestamp': k,
                    **v
                }
                for k, v in combined_data.items()
            ]
            
            # Sort by timestamp
            result.sort(key=lambda x: x['timestamp'])
            
            logger.info(f"Returning {len(result)} aggregated records")
            if len(result) > 0:
                logger.info(f"Sample result record: {result[0]}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error querying document token usage: {str(e)}", exc_info=True)
            return []

document_token_usage_repository = DocumentTokenUsageRepository() 