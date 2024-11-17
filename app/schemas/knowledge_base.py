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