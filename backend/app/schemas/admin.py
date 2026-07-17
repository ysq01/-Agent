from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AdminRole = Literal["admin", "operator"]
PolicyStatus = Literal["draft", "published", "disabled"]


class AdminSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class AdminLoginRequest(AdminSchema):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class AdminLoginResponse(AdminSchema):
    token: str
    role: AdminRole
    expires_at: datetime


class AdminLogoutResponse(AdminSchema):
    success: bool


class AdminPolicyCreateRequest(AdminSchema):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1)


class AdminPolicyUpdateRequest(AdminSchema):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = Field(default=None, min_length=1)

    @field_validator("title", "content", mode="after")
    @classmethod
    def empty_string_to_none(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def require_update_field(self) -> "AdminPolicyUpdateRequest":
        if self.title is None and self.content is None:
            raise ValueError("title or content is required")
        return self


class AdminPolicyResponse(AdminSchema):
    id: int
    title: str
    content: str
    status: PolicyStatus
    version: int
    source: str
    supersedes_policy_id: int | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    disabled_at: datetime | None


class AdminPolicyListResponse(AdminSchema):
    total: int
    policies: list[AdminPolicyResponse]


class AdminPolicyActionResponse(AdminSchema):
    policy: AdminPolicyResponse
    knowledge_updated: bool
