"""RAG corpus. Chunks are embedded and stored for grounded generation.

With ENABLE_PGVECTOR=true and the pgvector package installed, swap
``embedding`` for a ``Vector(1536)`` column and add an ivfflat index; the rest of
the retrieval code in app.services.rag does not change.
"""
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class KnowledgeDocument(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(60), default="brochure")
    source_uri: Mapped[str] = mapped_column(String(500), default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    approved_by: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class KnowledgeChunk(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
