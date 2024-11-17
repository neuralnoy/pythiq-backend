import boto3
from ..core.config import settings

def get_dynamodb_client():
    return boto3.resource('dynamodb',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION
    )

dynamodb = get_dynamodb_client()
users_table = dynamodb.Table('users')
knowledge_bases_table = dynamodb.Table('knowledge_bases')
