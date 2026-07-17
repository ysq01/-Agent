from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.dependencies import get_db_session
from app.schemas.evaluation import EvaluationHistoryResponse, LatestEvaluationResponse
from app.schemas.feedback import FeedbackSummaryResponse
from app.services import evaluation as evaluation_service
from app.services.feedback import get_feedback_summary


router = APIRouter(prefix="/api/eval", tags=["evaluation"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("/latest", response_model=LatestEvaluationResponse)
def get_latest_evaluation() -> LatestEvaluationResponse:
    try:
        return evaluation_service.read_latest_eval_report()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/history", response_model=EvaluationHistoryResponse)
def get_evaluation_history(
    limit: int = Query(default=20, ge=1, le=100),
) -> EvaluationHistoryResponse:
    return evaluation_service.read_eval_history(limit=limit)


@router.get("/feedback-summary", response_model=FeedbackSummaryResponse)
def get_agent_feedback_summary(session: DbSession) -> FeedbackSummaryResponse:
    return get_feedback_summary(session)
