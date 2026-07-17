from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.dependencies import get_db_session
from app.schemas.agent import AgentProcessRequest, AgentProcessResponse
from app.schemas.feedback import (
    AgentFeedbackCreateRequest,
    AgentFeedbackCreateResponse,
)
from app.services.agent_workflow import process_customer_message
from app.services.feedback import create_agent_feedback


router = APIRouter(prefix="/api/agent", tags=["agent"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post("/process", response_model=AgentProcessResponse)
def process_agent_message(
    request: AgentProcessRequest,
    session: DbSession,
) -> AgentProcessResponse:
    return process_customer_message(session, request)


@router.post(
    "/feedback",
    response_model=AgentFeedbackCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_agent_feedback(
    request: AgentFeedbackCreateRequest,
    session: DbSession,
) -> AgentFeedbackCreateResponse:
    return create_agent_feedback(session, request)
