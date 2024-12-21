from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class ChatBase(BaseModel):
    title: str
    knowledge_base_ids: List[str]

class ChatCreate(ChatBase):
    pass

class Chat(ChatBase):
    id: str
    user_id: str
    created_at: datetime
    last_modified: datetime
    token_count: int = 0
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ChatUpdate(BaseModel):
    title: Optional[str]
    knowledge_base_ids: Optional[List[str]] 