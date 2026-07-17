from app.schemas.knowledge import (
    KnowledgeDocumentListResponse,
    KnowledgeDocumentSummary,
)
from app.services.policy_knowledge import load_knowledge_documents
from sqlalchemy.orm import Session


PREVIEW_LENGTH = 160


def list_knowledge_documents(session: Session | None = None) -> KnowledgeDocumentListResponse:
    documents = load_knowledge_documents(session=session)
    summaries = [
        KnowledgeDocumentSummary(
            policy_title=document.policy_title,
            source_file=document.source_file,
            character_count=len(document.text),
            preview=_preview(document.text),
            content=document.text,
        )
        for document in documents
    ]
    return KnowledgeDocumentListResponse(total=len(summaries), documents=summaries)


def _preview(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:PREVIEW_LENGTH]
