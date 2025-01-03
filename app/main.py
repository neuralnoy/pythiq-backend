from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .auth.router import router as auth_router
from .api.v1.endpoints.knowledge_bases import router as knowledge_bases_router
from .api.v1.endpoints.documents import router as documents_router
from .api.v1.endpoints.chats import router as chats_router
from .api.v1.endpoints.usage import router as usage_router

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(knowledge_bases_router, prefix="/api/knowledge-bases", tags=["knowledge-bases"])
app.include_router(documents_router, prefix="/api/documents", tags=["documents"])
app.include_router(chats_router, prefix="/api/chats", tags=["chats"])
app.include_router(usage_router, prefix="/api/usage", tags=["usage"])
