from pydantic import BaseModel
from datetime import datetime
from typing import Optional

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
    parsing_status: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        } 