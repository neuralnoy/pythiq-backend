from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "us-east-1"
    AWS_BUCKET_NAME: str
    OPENAI_API_KEY: str
    ZILLIZ_CLOUD_URI: str
    ZILLIZ_CLOUD_API_KEY: str
    
    class Config:
        env_file = ".env"

settings = Settings()
