"""Create tables (and the pgvector extension when enabled)."""
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401,F403  -- registers all mappers

log = get_logger(__name__)


def init_db() -> None:
    if settings.enable_pgvector and settings.database_url.startswith("postgresql"):
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        log.info("pgvector extension ensured")
    Base.metadata.create_all(bind=engine)
    log.info("database schema ready (%s tables)", len(Base.metadata.tables))
