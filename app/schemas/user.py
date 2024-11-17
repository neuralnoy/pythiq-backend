from pydantic import BaseModel, EmailStr
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class User(UserBase):
    disabled: bool = False

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[dict] = None
