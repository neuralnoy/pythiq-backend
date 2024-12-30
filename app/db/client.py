import boto3
from ..core.config import settings
from boto3 import client
from boto3.dynamodb.conditions import Key
from boto3 import resource

def get_dynamodb_client():
    return boto3.resource('dynamodb',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION
    )

def get_s3_client():
    return client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION
    )

dynamodb = get_dynamodb_client()
users_table = dynamodb.Table('users')
knowledge_bases_table = dynamodb.Table('knowledge_bases')
s3_client = get_s3_client()
documents_table = dynamodb.Table('documents')
parsed_documents_table = dynamodb.Table('parsed_documents')
chats_table = dynamodb.Table('chats')
messages_table = dynamodb.Table('messages')
