from pydantic import BaseModel, EmailStr
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class User(UserBase):
    disabled: bool = False

class Token(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    user: Optional[dict] = None
