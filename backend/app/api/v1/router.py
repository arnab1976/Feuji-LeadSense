"""API v1 aggregate router."""
from fastapi import APIRouter

from app.api.v1 import (
    agents, analytics, auth, campaigns, emails, knowledge, leads, replies,
    sources, tenants,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(emails.router, prefix="/emails", tags=["emails"])
api_router.include_router(replies.router, prefix="/replies", tags=["replies"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
