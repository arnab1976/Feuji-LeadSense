from typing import Any

from pydantic import BaseModel, Field


class ConnectorDescriptor(BaseModel):
    key: str
    display_name: str
    description: str
    kind: str
    capabilities: list[str]
    requires_policy_review: bool
    config_fields: list[dict[str, Any]]


class SourceConnectionCreate(BaseModel):
    name: str
    connector_key: str
    config: dict[str, Any] = Field(default_factory=dict)
    policy_allowed: bool = True
    lawful_basis: str = "legitimate_interest"


class SourceConnectionUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    is_enabled: bool | None = None
    policy_allowed: bool | None = None
    lawful_basis: str | None = None


class SourceConnectionOut(BaseModel):
    id: str
    name: str
    connector_key: str
    kind: str = ""
    status: str
    is_enabled: bool
    policy_allowed: bool
    lawful_basis: str
    last_sync_at: str | None = None
    last_error: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class SyncRequest(BaseModel):
    limit: int = 50
    reset_cursor: bool = False
    run_pipeline: bool = True


class SyncResult(BaseModel):
    job_id: str
    connector_key: str
    fetched: int
    created: int
    duplicates: int
    invalid: int
    cursor: str = ""
    warnings: list[str] = Field(default_factory=list)
