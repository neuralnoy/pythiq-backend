from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class ParseStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ParsedDocument(BaseModel):
    id: str
    document_id: str
    knowledge_base_id: str
    user_id: str
    original_path: str
    parsed_path: str
    parse_status: ParseStatus
    parsed_at: datetime
    error_message: str | None = None
    metadata: dict = {}

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
