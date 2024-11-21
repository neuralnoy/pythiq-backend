from typing import List, Dict, Optional
from uuid import uuid4
from datetime import datetime, timezone
from ..client import s3_client
from ...core.config import settings

class DocumentRepository:
    async def upload_document(self, file, knowledge_base_id: str, user_id: str) -> Dict:
        file_id = str(uuid4())
        filename = file.filename
        content_type = file.content_type
        
        s3_client.upload_fileobj(
            file.file,
            settings.AWS_BUCKET_NAME,
            f"{user_id}/{knowledge_base_id}/{file_id}/{filename}",
            ExtraArgs={'ContentType': content_type}
        )
        
        return {
            "id": file_id,
            "name": filename,
            "type": content_type,
            "size": file.size,
            "knowledge_base_id": knowledge_base_id,
            "user_id": user_id,
            "path": f"{user_id}/{knowledge_base_id}/{file_id}/{filename}",
            "uploaded_at": datetime.now(timezone.utc)
        }

    async def get_documents(self, knowledge_base_id: str, user_id: str) -> List[Dict]:
        try:
            response = s3_client.list_objects_v2(
                Bucket=settings.AWS_BUCKET_NAME,
                Prefix=f"{user_id}/{knowledge_base_id}/"
            )
            
            if 'Contents' not in response:
                return []
                
            documents = []
            for obj in response['Contents']:
                # Skip if the object is a directory
                if obj['Key'].endswith('/'):
                    continue
                    
                documents.append({
                    "id": obj['Key'].split('/')[2],
                    "name": obj['Key'].split('/')[-1],
                    "size": obj['Size'],
                    "type": obj.get('ContentType', 'application/octet-stream'),
                    "knowledge_base_id": knowledge_base_id,
                    "user_id": user_id,
                    "path": obj['Key'],
                    "uploaded_at": obj['LastModified']
                })
            
            return documents
        except Exception as e:
            print(f"Error fetching documents: {str(e)}")
            return []

    async def delete_document(self, document_id: str, knowledge_base_id: str, user_id: str) -> bool:
        try:
            response = s3_client.list_objects_v2(
                Bucket=settings.AWS_BUCKET_NAME,
                Prefix=f"{user_id}/{knowledge_base_id}/{document_id}/"
            )
            
            for obj in response.get('Contents', []):
                s3_client.delete_object(
                    Bucket=settings.AWS_BUCKET_NAME,
                    Key=obj['Key']
                )
            return True
        except Exception:
            return False

    async def rename_document(self, document_id: str, knowledge_base_id: str, user_id: str, new_name: str) -> Optional[Dict]:
        try:
            # Get the old document info
            response = s3_client.list_objects_v2(
                Bucket=settings.AWS_BUCKET_NAME,
                Prefix=f"{user_id}/{knowledge_base_id}/{document_id}/"
            )
            
            if 'Contents' not in response:
                return None
                
            old_key = response['Contents'][0]['Key']
            new_key = f"{user_id}/{knowledge_base_id}/{document_id}/{new_name}"
            
            # Copy to new name
            s3_client.copy_object(
                Bucket=settings.AWS_BUCKET_NAME,
                CopySource={'Bucket': settings.AWS_BUCKET_NAME, 'Key': old_key},
                Key=new_key
            )
            
            # Delete old object
            s3_client.delete_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=old_key
            )
            
            return {
                "id": document_id,
                "name": new_name,
                "knowledge_base_id": knowledge_base_id,
                "user_id": user_id
            }
        except Exception:
            return None

    async def generate_download_url(self, document_id: str, knowledge_base_id: str, user_id: str) -> Optional[str]:
        try:
            response = s3_client.list_objects_v2(
                Bucket=settings.AWS_BUCKET_NAME,
                Prefix=f"{user_id}/{knowledge_base_id}/{document_id}/"
            )
            
            if 'Contents' not in response:
                return None
                
            key = response['Contents'][0]['Key']
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.AWS_BUCKET_NAME,
                    'Key': key
                },
                ExpiresIn=3600  # URL expires in 1 hour
            )
            return url
        except Exception:
            return None

document_repository = DocumentRepository()