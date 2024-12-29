from typing import Dict
import httpx
import logging
from ..core.config import settings

logger = logging.getLogger(__name__)

class ParserService:
    def __init__(self):
        self.parser_url = "http://localhost:8001/api/v1/process"
        # Increase timeouts significantly for large documents
        self.timeout = httpx.Timeout(
            timeout=2700.0,  # 30 minutes total timeout
            connect=300.0,   # 5 minutes connection timeout
            read=2700.0,     # 30 minutes read timeout
            write=300.0      # 5 minutes write timeout
        )

    async def start_parsing(self, document: Dict):
        try:
            logger.info(f"Starting parsing for document: {document['id']}")
            
            # Extract components from the S3 path
            # Path format: user_id/knowledge_base_id/document_id/filename
            path_parts = document['path'].split('/')
            
            # Prepare the exact payload the parser expects
            payload = {
                "document_id": document['id'],
                "knowledge_base_id": document['knowledge_base_id'],
                "user_id": document['user_id'],
                "file_path": document['path'],
                "output_prefix": f"{'/'.join(path_parts[:-1])}/processed"
            }

            logger.info(f"Calling parser service with payload: {payload}")

            # Call the parser service with timeout
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.parser_url,
                    json=payload
                )
                
                logger.info(f"Parser service response: {response.status_code} - {response.text}")
                
                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get('status') == 'success':
                        # Update status to done only when parser returns success
                        from ..db.repositories.documents import document_repository
                        await document_repository.update_parsing_status(
                            document['knowledge_base_id'],
                            document['id'],
                            'done',
                            document['user_id']
                        )
                        logger.info(f"Parsing completed successfully for document: {document['id']}")
                        return response_data
                    
                logger.error(f"Parser service error: {response.text}")
                from ..db.repositories.documents import document_repository
                await document_repository.update_parsing_status(
                    document['knowledge_base_id'],
                    document['id'],
                    'failed',
                    document['user_id']
                )
                raise Exception(f"Parser service returned error: {response.text}")
                
        except httpx.TimeoutException as e:
            logger.error(f"Timeout during parsing: {str(e)}")
            # Update document status to failed on timeout
            from ..db.repositories.documents import document_repository
            await document_repository.update_parsing_status(
                document['knowledge_base_id'],
                document['id'],
                'failed',
                document['user_id']
            )
            raise
        except Exception as e:
            logger.error(f"Error during parsing: {str(e)}")
            # Update document status to failed on any other error
            from ..db.repositories.documents import document_repository
            await document_repository.update_parsing_status(
                document['knowledge_base_id'],
                document['id'],
                'failed',
                document['user_id']
            )
            raise

parser_service = ParserService()
