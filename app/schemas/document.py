from pydantic import BaseModel
from datetime import datetime

class Document(BaseModel):
    id: str
    name: str
    type: str
    size: int
    knowledge_base_id: str
    user_id: str
    path: str
    uploaded_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        } 