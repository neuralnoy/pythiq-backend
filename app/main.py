from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .auth.router import router as auth_router
from .api.v1.endpoints.knowledge_bases import router as knowledge_bases_router

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Add your React app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(knowledge_bases_router, prefix="/api/knowledge-bases", tags=["knowledge-bases"])
