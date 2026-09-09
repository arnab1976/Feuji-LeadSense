"""Agent 07 - Segmentation."""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import Lead, LeadEnrichment, LeadScore, Segment, SegmentMember


class SegmentationAgent(BaseAgent):
    key = "segmentation"
    name = "Segmentation"
    role = "Groups leads into actionable audiences"
    inputs = "Lead features, embeddings, campaign objective, tenant segmentation rules"
    execution_strategy = (
        "Apply deterministic filters; optionally cluster similar leads; label the "
        "clusters; validate minimum segment size."
    )
    outputs = "Segment assignment, confidence, segment explanation"
    stack = "Rules, embeddings, scikit-learn or HDBSCAN optional, LLM labelling"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        min_score: int = kwargs.get("min_score", 70)
        group_by: str = kwargs.get("group_by", "persona")
        min_size: int = kwargs.get("min_size", 2)
        industries: list[str] = kwargs.get("industries") or []
        persist: bool = kwargs.get("persist", True)

        rows = (
            ctx.db.query(Lead, LeadScore, LeadEnrichment)
            .join(LeadScore, LeadScore.lead_id == Lead.id)
            .outerjoin(LeadEnrichment, LeadEnrichment.lead_id == Lead.id)
            .filter(Lead.tenant_id == ctx.tenant_id,
                    LeadScore.score >= min_score,
                    Lead.duplicate_of_id.is_(None))
            .all()
        )
        if industries:
            wanted = {i.lower() for i in industries}
            rows = [r for r in rows
                    if (r[2].industry if r[2] else "").lower() in wanted]

        buckets: dict[str, list] = {}
        for lead, score, enrichment in rows:
            if group_by == "industry":
                key = (enrichment.industry if enrichment else "") or "Unknown industry"
            elif group_by == "seniority":
                key = (enrichment.seniority if enrichment else "") or "Unclassified"
            else:
                key = (enrichment.persona if enrichment else "") or "General business"
            buckets.setdefault(key, []).append((lead, score))

        segments: list[dict] = []
        for name, members in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            viable = len(members) >= min_size
            avg = round(sum(s.score for _, s in members) / len(members))
            entry = {
                "name": name, "size": len(members), "viable": viable,
                "average_score": avg,
                "lead_ids": [lead.id for lead, _ in members],
                "explanation": (f"{len(members)} leads grouped by {group_by} "
                                f"with a score of {min_score} or above"),
            }
            if persist and viable:
                segment = Segment(
                    tenant_id=ctx.tenant_id, name=name,
                    description=entry["explanation"], method="rules",
                    rules={"min_score": min_score, "group_by": group_by,
                           "industries": industries},
                    size=len(members), confidence=0.9,
                )
                ctx.db.add(segment)
                ctx.db.flush()
                for lead, _ in members:
                    ctx.db.add(SegmentMember(tenant_id=ctx.tenant_id,
                                             segment_id=segment.id, lead_id=lead.id))
                entry["segment_id"] = segment.id
            segments.append(entry)

        ctx.db.flush()
        viable_count = sum(1 for s in segments if s["viable"])
        return AgentResult(
            output={"segments": segments, "qualified_leads": len(rows)},
            decision="SEGMENTED" if viable_count else "NO_VIABLE_SEGMENT",
            confidence=0.9,
            reason=f"{viable_count} viable segments from {len(rows)} qualified leads",
        )
