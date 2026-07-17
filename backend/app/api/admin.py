from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.dependencies import get_db_session
from app.models import AdminUser
from app.schemas.admin import (
    AdminPolicyActionResponse,
    AdminPolicyCreateRequest,
    AdminPolicyListResponse,
    AdminPolicyResponse,
    AdminPolicyUpdateRequest,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminLogoutResponse,
    PolicyStatus,
)
from app.schemas.evaluation import (
    EvaluationCompareResponse,
    LlmAssistedEvaluationJobStatus,
)
from app.services import admin_auth
from app.services import admin_policies
from app.services import evaluation as evaluation_service
from app.services import evaluation_jobs
from app.services.admin_policies import AdminPolicyError
from app.services.evaluation_jobs import EvaluationJobError


router = APIRouter(prefix="/api/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(get_db_session)]
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_admin(
    session: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AdminUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_admin_unauthorized()

    admin = admin_auth.get_admin_by_token(session, credentials.credentials)
    if admin is None:
        raise_admin_unauthorized()
    return admin


CurrentAdmin = Annotated[AdminUser, Depends(get_current_admin)]


@router.post("/login", response_model=AdminLoginResponse)
def login_admin(
    request: AdminLoginRequest,
    session: DbSession,
) -> AdminLoginResponse:
    login = admin_auth.authenticate_admin(
        session,
        username=request.username,
        password=request.password,
    )
    if login is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码不正确，请检查后重试。",
        )

    return AdminLoginResponse(
        token=login.token,
        role=login.role,  # type: ignore[arg-type]
        expires_at=login.expires_at,
    )


@router.post("/logout", response_model=AdminLogoutResponse)
def logout_admin(
    session: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AdminLogoutResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_admin_unauthorized()

    admin_auth.revoke_admin_session(session, credentials.credentials)
    return AdminLogoutResponse(success=True)


@router.get("/eval/compare", response_model=EvaluationCompareResponse)
def compare_evaluation_reports(
    _admin: CurrentAdmin,
) -> EvaluationCompareResponse:
    return evaluation_service.read_eval_comparison()


@router.post(
    "/eval/llm-assisted/run",
    response_model=LlmAssistedEvaluationJobStatus,
)
def run_llm_assisted_evaluation(
    background_tasks: BackgroundTasks,
    _admin: CurrentAdmin,
) -> LlmAssistedEvaluationJobStatus:
    try:
        result = evaluation_jobs.start_llm_assisted_evaluation_job()
    except EvaluationJobError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    if result.started:
        background_tasks.add_task(evaluation_jobs.run_llm_assisted_evaluation_job)
    return result.status


@router.get(
    "/eval/llm-assisted/status",
    response_model=LlmAssistedEvaluationJobStatus,
)
def get_llm_assisted_evaluation_status(
    _admin: CurrentAdmin,
) -> LlmAssistedEvaluationJobStatus:
    return evaluation_jobs.get_llm_assisted_evaluation_status()


@router.get("/policies", response_model=AdminPolicyListResponse)
def list_policies(
    session: DbSession,
    _admin: CurrentAdmin,
    policy_status: Annotated[PolicyStatus | None, Query(alias="status")] = None,
) -> AdminPolicyListResponse:
    policies = admin_policies.list_admin_policies(session, policy_status)
    return AdminPolicyListResponse(
        total=len(policies),
        policies=[AdminPolicyResponse.model_validate(policy) for policy in policies],
    )


@router.post(
    "/policies",
    response_model=AdminPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_policy(
    request: AdminPolicyCreateRequest,
    session: DbSession,
    admin: CurrentAdmin,
) -> AdminPolicyResponse:
    policy = admin_policies.create_policy(session, request, admin)
    return AdminPolicyResponse.model_validate(policy)


@router.patch("/policies/{policy_id}", response_model=AdminPolicyResponse)
def update_policy(
    policy_id: int,
    request: AdminPolicyUpdateRequest,
    session: DbSession,
    admin: CurrentAdmin,
) -> AdminPolicyResponse:
    try:
        policy = admin_policies.update_policy(session, policy_id, request, admin)
    except AdminPolicyError as error:
        raise_policy_error(error)
    return AdminPolicyResponse.model_validate(policy)


@router.post("/policies/{policy_id}/publish", response_model=AdminPolicyActionResponse)
def publish_policy(
    policy_id: int,
    session: DbSession,
    admin: CurrentAdmin,
) -> AdminPolicyActionResponse:
    try:
        policy = admin_policies.publish_policy(session, policy_id, admin)
    except AdminPolicyError as error:
        raise_policy_error(error)
    return AdminPolicyActionResponse(
        policy=AdminPolicyResponse.model_validate(policy),
        knowledge_updated=True,
    )


@router.post("/policies/{policy_id}/disable", response_model=AdminPolicyActionResponse)
def disable_policy(
    policy_id: int,
    session: DbSession,
    admin: CurrentAdmin,
) -> AdminPolicyActionResponse:
    try:
        policy = admin_policies.disable_policy(session, policy_id, admin)
    except AdminPolicyError as error:
        raise_policy_error(error)
    return AdminPolicyActionResponse(
        policy=AdminPolicyResponse.model_validate(policy),
        knowledge_updated=True,
    )


def raise_admin_unauthorized() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="请先登录后台管理。",
    )


def raise_policy_error(error: AdminPolicyError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.message)
