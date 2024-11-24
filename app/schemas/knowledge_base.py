from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class KnowledgeBaseBase(BaseModel):
    title: str

class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass

class KnowledgeBase(KnowledgeBaseBase):
    id: str
    user_id: str
    created_at: datetime
    document_count: int = 0

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        } 

class KnowledgeBaseUpdate(BaseModel):
    title: str 