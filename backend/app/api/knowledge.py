from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.dependencies import get_db_session
from app.schemas.knowledge import KnowledgeDocumentListResponse
from app.services.knowledge_documents import list_knowledge_documents


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
def get_knowledge_documents(session: DbSession) -> KnowledgeDocumentListResponse:
    return list_knowledge_documents(session)
