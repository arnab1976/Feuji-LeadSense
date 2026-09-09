"""Agent 04 - Verification. The product's signature capability.

Three tiers, cheapest first: exact rule comparison, then fuzzy string matching,
then semantic similarity. An LLM is only consulted for genuinely ambiguous cases,
which keeps cost proportional to difficulty.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import Lead, LeadExtraction, LeadVerification
from app.services.embeddings import cosine, embed
from app.services.taxonomy import normalize_title

COMPARED_FIELDS = [
    ("title", "title", 0.86, 0.62),
    ("company_name", "company_name", 0.90, 0.70),
    ("location", "location", 0.80, 0.55),
    ("email", "email", 0.99, 0.85),
]

#: Words that carry no meaning when comparing two renderings of the same title.
TITLE_STOPWORDS = {"of", "the", "and", "for", "to", "at", "in"}

LEGAL_SUFFIXES = {"ltd", "limited", "plc", "inc", "corp", "gmbh", "ag", "sa", "as",
                  "a/s", "ab", "kk", "sl", "pvt", "llc", "group", "partners", "co",
                  "pjsc", "sas"}


def _title_key(title: str) -> str:
    """Comparable form of a title: expanded, stopword-free, order-insensitive."""
    words = [w for w in normalize_title(title).lower().split()
             if w not in TITLE_STOPWORDS]
    return " ".join(words)


def _strip_entity(name: str) -> str:
    words = [w.strip(".,").lower() for w in (name or "").split()]
    return " ".join(w for w in words if w not in LEGAL_SUFFIXES)


class VerificationAgent(BaseAgent):
    key = "verification"
    name = "Verification"
    summary = "Compares extracted fields and pauses for human review"
    definition = (
        "Human-in-the-loop gate that matches extracted values to source evidence "
        "and opens conflicts when fields disagree."
    )
    description = (
        "Pauses the pipeline when confidence or source match fails. Reviewers "
        "resolve conflicts in the workbench; once clear, the Orchestrator resumes "
        "Enrichment and Scoring."
    )
    role = "Conflict detection · human gate · approved field write-back"
    stage = "3. Verification"
    inputs = "Uploaded lead fields, extracted fields, tenant thresholds"
    execution_strategy = (
        "Exact and rule comparison; fuzzy matching; semantic comparison where "
        "needed; classify; compute confidence; route mismatch and review cases."
    )
    outputs = "MATCH / MISMATCH / NEEDS_REVIEW, confidence, field-level reasons"
    stack = "Rule engine, RapidFuzz, embeddings for ambiguous cases, FastAPI"
    version = "verification-v1"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        leads: list[Lead] = kwargs["leads"]
        counts = {"MATCH": 0, "MISMATCH": 0, "NEEDS_REVIEW": 0}
        rows: list[dict] = []

        for lead in leads:
            extraction = (
                ctx.db.query(LeadExtraction)
                .filter(LeadExtraction.lead_id == lead.id,
                        LeadExtraction.status == "extracted")
                .order_by(LeadExtraction.created_at.desc())
                .first()
            )
            if not extraction:
                continue

            ctx.db.query(LeadVerification).filter(
                LeadVerification.lead_id == lead.id
            ).delete()

            lead_open = False
            for field, payload_key, match_at, review_at in COMPARED_FIELDS:
                uploaded = str(getattr(lead, field, "") or "").strip()
                extracted = str((extraction.payload or {}).get(payload_key, "") or "").strip()
                if not uploaded and not extracted:
                    continue

                status, confidence, reason, method = self._compare(
                    field, uploaded, extracted, match_at, review_at
                )
                counts[status] = counts.get(status, 0) + 1
                if status != "MATCH":
                    lead_open = True

                ctx.db.add(LeadVerification(
                    tenant_id=ctx.tenant_id, lead_id=lead.id, field=field,
                    uploaded_value=uploaded, extracted_value=extracted,
                    status=status, confidence=round(confidence, 3),
                    reason=reason, method=method,
                    resolved_value=extracted if status == "MATCH" else "",
                    resolved_source="auto" if status == "MATCH" else "",
                ))
                rows.append({"lead_id": lead.id, "field": field, "status": status,
                             "confidence": round(confidence, 3)})

            lead.status = "needs_review" if lead_open else "verified"

        ctx.db.flush()
        open_count = counts["MISMATCH"] + counts["NEEDS_REVIEW"]
        return AgentResult(
            output={"counts": counts, "rows": rows, "open_conflicts": open_count},
            decision="NEEDS_REVIEW" if open_count else "MATCH",
            confidence=0.92,
            reason=(f"{counts['MATCH']} match, {counts['MISMATCH']} mismatch, "
                    f"{counts['NEEDS_REVIEW']} need review"),
            requires_human=open_count > 0,
            pause_reason="conflict_resolution" if open_count else "",
        )

    def _compare(self, field, uploaded, extracted, match_at, review_at):
        if not uploaded or not extracted:
            return ("NEEDS_REVIEW", 0.5,
                    f"{field.replace('_', ' ')} present on only one side", "rule")

        if uploaded.strip().lower() == extracted.strip().lower():
            return "MATCH", 0.99, "Uploaded and extracted values are identical", "rule"

        if field == "title":
            if _title_key(uploaded) == _title_key(extracted):
                return ("MATCH", 0.96,
                        "Titles are equivalent once abbreviations are expanded and "
                        "filler words are removed", "rule")
        if field == "company_name":
            if _strip_entity(uploaded) == _strip_entity(extracted):
                return ("MATCH", 0.95,
                        "Company names match once the legal suffix is removed", "rule")

        ratio = fuzz.token_sort_ratio(uploaded.lower(), extracted.lower()) / 100
        if ratio >= match_at:
            return ("MATCH", ratio,
                    f"Fuzzy token similarity {ratio:.2f} is above the tenant "
                    f"match threshold", "fuzzy")

        semantic = cosine(embed(uploaded), embed(extracted))
        blended = max(ratio, semantic)
        if blended >= match_at:
            return ("MATCH", blended,
                    "Values are semantically equivalent", "semantic")
        if blended >= review_at:
            return ("NEEDS_REVIEW", blended,
                    "Fuzzy and semantic similarity fell between the tenant "
                    "thresholds", "semantic")
        return ("MISMATCH", blended,
                f"{field.replace('_', ' ').capitalize()} differs materially from the "
                f"uploaded value", "semantic")
