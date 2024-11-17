from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from ..core.config import settings
from ..core.security import verify_password, get_password_hash, create_access_token
from ..schemas.user import UserCreate, Token
from ..db.repositories.users import user_repository

router = APIRouter()

@router.post("/register", response_model=Token)
async def register(user_data: UserCreate):
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
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"email": user_data.email}
    }

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await user_repository.get_by_email(form_data.username)
    if not user or not verify_password(form_data.password, user['hashed_password']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    access_token = create_access_token(
        data={"sub": user['email']},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"email": user['email']}
    }
