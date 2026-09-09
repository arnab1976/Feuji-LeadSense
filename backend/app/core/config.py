"""Application settings, loaded from environment variables or a .env file."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- app ---
    app_name: str = "LeadSense"
    environment: str = "local"
    debug: bool = True
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- database ---
    database_url: str = "sqlite:///./leadsense.db"
    enable_pgvector: bool = False

    # --- redis / celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_always_eager: bool = True

    # --- identity ---
    auth_mode: Literal["dev", "entra"] = "dev"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_audience: str = ""

    # --- llm ---
    llm_provider: Literal["echo", "anthropic", "openai", "azure_openai"] = "echo"
    llm_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    embedding_model: str = "text-embedding-3-small"

    # --- email ---
    email_provider: Literal["console", "ses"] = "console"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    ses_from_address: str = "no-reply@example.com"
    ses_configuration_set: str = ""

    # --- storage ---
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_dir: str = "./uploads"
    s3_bucket: str = ""

    # --- connectors ---
    demo_connectors: bool = True
    salesforce_domain: str = ""
    salesforce_client_id: str = ""
    salesforce_client_secret: str = ""
    salesforce_username: str = ""
    salesforce_password: str = ""
    salesforce_api_version: str = "v60.0"
    hubspot_access_token: str = ""
    apollo_api_key: str = ""
    apollo_base_url: str = "https://api.apollo.io/v1"
    zoominfo_username: str = ""
    zoominfo_password: str = ""

    # --- observability ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    otel_exporter_otlp_endpoint: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
