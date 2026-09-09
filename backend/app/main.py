"""LeadSense API entry point."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import LeadSenseError
from app.core.logging import configure_logging, get_logger
from app.db.init_db import init_db

configure_logging("DEBUG" if settings.debug else "INFO")
log = get_logger("leadsense.api")

app = FastAPI(
    title="LeadSense API",
    version=__version__,
    description=(
        "Agentic AI lead intelligence and sales engagement platform. "
        "Thirteen agents, a pluggable source connector layer and human gates on "
        "every material action."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LeadSenseError)
async def leadsense_error_handler(request: Request, exc: LeadSenseError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    log.info("%s API ready in %s mode (auth=%s, llm=%s, email=%s)",
             settings.app_name, settings.environment, settings.auth_mode,
             settings.llm_provider, settings.email_provider)


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__,
            "environment": settings.environment}


app.include_router(api_router, prefix=settings.api_prefix)
