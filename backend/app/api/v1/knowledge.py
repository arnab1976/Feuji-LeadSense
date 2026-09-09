"""Approved knowledge corpus for RAG grounding."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.errors import NotFound
from app.models import KnowledgeChunk, KnowledgeDocument
from app.services.rag import index_document, retrieve

router = APIRouter()


@router.get("/documents")
def list_documents(db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == user.tenant_id)
    ).all()
    return [{
        "id": d.id, "title": d.title, "doc_type": d.doc_type, "approved": d.approved,
        "approved_by": d.approved_by, "source_uri": d.source_uri,
        "chunks": db.query(KnowledgeChunk).filter(
            KnowledgeChunk.document_id == d.id).count(),
        "preview": (d.content or "")[:180],
    } for d in rows]


@router.post("/documents")
def create_document(body: dict, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_permission("campaign:write"))):
    doc = KnowledgeDocument(
        tenant_id=user.tenant_id, title=body["title"],
        doc_type=body.get("doc_type", "brochure"), content=body.get("content", ""),
        source_uri=body.get("source_uri", ""), approved=bool(body.get("approved")),
        approved_by=user.name if body.get("approved") else "",
    )
    db.add(doc)
    db.flush()
    chunks = index_document(db, doc)
    db.commit()
    return {"id": doc.id, "chunks": chunks}


@router.post("/documents/{document_id}/approve")
def approve_document(document_id: str, body: dict | None = None,
                     db: Session = Depends(get_db),
                     user: CurrentUser = Depends(require_permission("campaign:write"))):
    """Approval is the control that decides what agents may cite."""
    doc = db.get(KnowledgeDocument, document_id)
    if not doc or doc.tenant_id != user.tenant_id:
        raise NotFound("Document not found")
    approved = True if body is None else bool(body.get("approved", True))
    doc.approved = approved
    doc.approved_by = user.name if approved else ""
    if approved:
        index_document(db, doc)
    db.commit()
    return {"id": doc.id, "approved": doc.approved}


@router.get("/search")
def search(q: str, k: int = 4, db: Session = Depends(get_db),
           user: CurrentUser = Depends(get_current_user)):
    return retrieve(db, user.tenant_id, q, k=k)
