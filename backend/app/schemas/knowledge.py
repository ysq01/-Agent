from pydantic import BaseModel, ConfigDict


class KnowledgeReadSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class KnowledgeDocumentSummary(KnowledgeReadSchema):
    policy_title: str
    source_file: str
    character_count: int
    preview: str
    content: str


class KnowledgeDocumentListResponse(KnowledgeReadSchema):
    total: int
    documents: list[KnowledgeDocumentSummary]
