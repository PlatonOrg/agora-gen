from fastapi import APIRouter
from src.api.v1.endpoints import (
    auth,
    context,
    chat,
    exercises,
    platon_docs_qa,
    logs,
    admin,
    components,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(context.router, prefix="/context", tags=["Context"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(platon_docs_qa.router, prefix="/chat", tags=["Chat"])
api_router.include_router(exercises.router)
api_router.include_router(logs.router, prefix="/logs", tags=["Logs"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(components.router, prefix="/components", tags=["Components"])
