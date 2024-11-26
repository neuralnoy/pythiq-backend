from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from enum import Enum

class Document(BaseModel):
    id: str
    name: str
    type: str
    size: int
    knowledge_base_id: str
    user_id: str
    path: str
    uploaded_at: datetime
    enabled: bool = True
    updated_at: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        } 

class DocumentUploadError(BaseModel):
    filename: str
    error: str

class DocumentUploadResponse(BaseModel):
    documents: List[Document]
    errors: List[DocumentUploadError] 