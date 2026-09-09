"""Retrieval over the approved knowledge corpus.

Only documents with ``approved=True`` are ever retrievable. That is the control
that stops the email agent inventing claims: if a fact is not in an approved
document, the agent has no way to cite it.

To move to pgvector, replace the Python cosine ranking in ``retrieve`` with an
``ORDER BY embedding <=> :query_vector`` clause. Nothing else changes.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument
from app.services.embeddings import cosine, embed

CHUNK_TARGET_CHARS = 700


def chunk_text(text: str, target: int = CHUNK_TARGET_CHARS) -> list[str]:
    """Section-aware chunking: split on blank lines, then pack to target size."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        if len(buffer) + len(para) + 2 <= target:
            buffer = f"{buffer}\n\n{para}" if buffer else para
        else:
            if buffer:
                chunks.append(buffer)
            buffer = para
    if buffer:
        chunks.append(buffer)
    return chunks or [text.strip()]


def index_document(db: Session, doc: KnowledgeDocument) -> int:
    """(Re)build the chunk index for one document."""
    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).delete()
    created = 0
    for ordinal, text in enumerate(chunk_text(doc.content)):
        db.add(KnowledgeChunk(
            tenant_id=doc.tenant_id, document_id=doc.id, ordinal=ordinal,
            text=text, embedding=embed(text), token_count=max(1, len(text) // 4),
        ))
        created += 1
    db.flush()
    return created


def retrieve(
    db: Session, tenant_id: str, query: str, k: int = 4,
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Metadata-filtered semantic search across approved documents only."""
    stmt = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeChunk.tenant_id == tenant_id,
            KnowledgeDocument.approved.is_(True),
        )
    )
    if document_ids:
        stmt = stmt.where(KnowledgeDocument.id.in_(document_ids))

    query_vec = embed(query)
    scored = []
    for chunk, doc in db.execute(stmt).all():
        scored.append({
            "document_id": doc.id,
            "document_title": doc.title,
            "doc_type": doc.doc_type,
            "chunk_id": chunk.id,
            "text": chunk.text,
            "score": round(cosine(query_vec, chunk.embedding or []), 4),
        })
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:k]


def groundedness(cited: list[dict]) -> float:
    """Crude but honest: confidence rises with how well the corpus matched."""
    if not cited:
        return 0.0
    best = max(c["score"] for c in cited)
    return round(min(0.97, 0.55 + best * 0.45), 3)
