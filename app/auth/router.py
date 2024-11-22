from fastapi import APIRouter, Depends, HTTPException, status, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from ..core.config import settings
from ..core.security import verify_password, get_password_hash, create_access_token
from ..schemas.user import UserCreate, Token
from ..db.repositories.users import user_repository
from .deps import get_current_user

router = APIRouter()

@router.post("/register")
async def register(response: Response, user_data: UserCreate):
    if await user_repository.get_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    user_dict = {
        'email': user_data.email,
        'hashed_password': get_password_hash(user_data.password),
        'disabled': False
    }
    
    await user_repository.create(user_dict)
    
    access_token = create_access_token(
        data={"sub": user_data.email},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=True,
        samesite='lax',
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    return {
        "user": {"email": user_data.email}
    }

@router.post("/login")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), remember_me: bool = Form(default=False)):
    user = await user_repository.get_by_email(form_data.username)
    if not user or not verify_password(form_data.password, user['hashed_password']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    expires_delta = timedelta(days=30) if remember_me else timedelta(hours=24)
    
    access_token = create_access_token(
        data={"sub": user['email']},
        expires_delta=expires_delta
    )
    
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=True,
        samesite='lax',
        max_age=int(expires_delta.total_seconds())
    )
    
    return {
        "user": {"email": user['email']}
    }

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}

@router.get("/me")
async def get_current_user(current_user = Depends(get_current_user)):
    return {"user": current_user}