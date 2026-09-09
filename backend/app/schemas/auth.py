from pydantic import BaseModel, Field


class DevTokenRequest(BaseModel):
    email: str = "arnab.das@feuji.com"
    name: str = "Arnab Das"
    role: str = Field(default="sales_manager")
    tenant_slug: str = "feuji-revops"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: dict


class MeResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    tenant_id: str
    tenant_name: str
    permissions: list[str]
