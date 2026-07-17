from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.session import make_engine
from app.schemas.evaluation import EvaluationReport, LlmAssistedEvaluationJobStatus
from app.services.evaluation import (
    DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH,
    DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH,
    load_eval_cases,
    run_evaluation,
    write_evaluation_reports,
)


MISSING_API_KEY_MESSAGE = (
    "增强模式未配置 API Key，请先在后端环境变量中配置 "
    "DASHSCOPE_API_KEY 后重启服务。"
)
IDLE_MESSAGE = "尚未触发增强模式评测。"
RUNNING_MESSAGE = "增强模式评测正在生成，请稍后查看。"
SUCCEEDED_MESSAGE = "增强模式评测已生成，正在刷新对比结果。"
FAILED_MESSAGE = "增强模式评测生成失败，请检查后端评测依赖后重试。"


class EvaluationJobError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluationJobStartResult:
    status: LlmAssistedEvaluationJobStatus
    started: bool


_lock = threading.Lock()
_job_status = LlmAssistedEvaluationJobStatus(
    status="idle",
    message=IDLE_MESSAGE,
)


def get_llm_assisted_evaluation_status() -> LlmAssistedEvaluationJobStatus:
    with _lock:
        return _job_status.model_copy(deep=True)


def start_llm_assisted_evaluation_job() -> EvaluationJobStartResult:
    if not os.getenv("DASHSCOPE_API_KEY", "").strip():
        raise EvaluationJobError(MISSING_API_KEY_MESSAGE)

    global _job_status
    now = datetime.now(UTC)
    with _lock:
        if _job_status.status == "running":
            return EvaluationJobStartResult(
                status=_job_status.model_copy(deep=True),
                started=False,
            )

        _job_status = LlmAssistedEvaluationJobStatus(
            status="running",
            message=RUNNING_MESSAGE,
            started_at=now,
            finished_at=None,
            report_generated_at=None,
        )
        return EvaluationJobStartResult(
            status=_job_status.model_copy(deep=True),
            started=True,
        )


def run_llm_assisted_evaluation_job() -> None:
    global _job_status
    try:
        report = _execute_llm_assisted_evaluation()
    except Exception:
        with _lock:
            _job_status = _job_status.model_copy(
                update={
                    "status": "failed",
                    "message": FAILED_MESSAGE,
                    "finished_at": datetime.now(UTC),
                },
                deep=True,
            )
        return

    with _lock:
        _job_status = _job_status.model_copy(
            update={
                "status": "succeeded",
                "message": SUCCEEDED_MESSAGE,
                "finished_at": datetime.now(UTC),
                "report_generated_at": report.generated_at,
            },
            deep=True,
        )


def _execute_llm_assisted_evaluation() -> EvaluationReport:
    cases = load_eval_cases()
    engine = make_engine()
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            session = Session(
                bind=connection,
                autoflush=False,
                expire_on_commit=False,
            )
            try:
                report = run_evaluation(session, cases, mode="llm_assisted")
            finally:
                session.close()
                transaction.rollback()

        write_evaluation_reports(
            report,
            json_path=DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH,
            markdown_path=DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH,
            write_history=True,
        )
        return report
    finally:
        engine.dispose()


def reset_llm_assisted_evaluation_job_for_tests() -> None:
    global _job_status
    with _lock:
        _job_status = LlmAssistedEvaluationJobStatus(
            status="idle",
            message=IDLE_MESSAGE,
        )
