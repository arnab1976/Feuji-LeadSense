"""Agent 10 - Compliance & Quality.

Six checks, run before a human ever sees a draft. Any failure in source policy,
lawful basis, suppression or prohibited claims is a hard BLOCK: the API refuses
to approve those emails at all, rather than leaving it to a reviewer's judgement.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import ComplianceCheck, EmailSendJob, GeneratedEmail, Lead
from app.services import policy

HARD_FAIL_CHECKS = {"source_policy", "lawful_basis", "suppression", "prohibited_claims"}
BANNED_PHRASES = ["guaranteed", "risk free", "no obligation whatsoever",
                  "best in the world", "outperforms every"]


class ComplianceAgent(BaseAgent):
    key = "compliance"
    name = "Compliance & Quality"
    role = "Checks policy, suppression, quality and risk"
    inputs = ("Generated email, lead metadata, source and lawful-basis state, "
              "tenant policy, suppression list")
    execution_strategy = (
        "Check source policy, lawful basis and consent state, suppression and "
        "unsubscribe, duplicate contact, prohibited content, tenant policy and "
        "content quality."
    )
    outputs = "APPROVE_FOR_REVIEW / BLOCK / NEEDS_REVIEW, risk score, reasons"
    stack = "Rules, policy service, suppression store, optional LLM quality classifier"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        emails: list[GeneratedEmail] = kwargs["emails"]
        sending_policy = policy.get_policy(ctx.db, ctx.tenant_id).sending_policy or {}
        window_days = int(sending_policy.get("duplicate_contact_window_days", 30))

        verdicts = {"APPROVE_FOR_REVIEW": 0, "NEEDS_REVIEW": 0, "BLOCK": 0}
        results: list[dict] = []

        for email in emails:
            lead = ctx.db.get(Lead, email.lead_id)
            checks = self._run_checks(ctx, email, lead, window_days)
            failed = [c for c in checks if not c["pass"]]
            hard = [c for c in failed if c["key"] in HARD_FAIL_CHECKS]

            verdict = "BLOCK" if hard else ("NEEDS_REVIEW" if failed
                                            else "APPROVE_FOR_REVIEW")
            risk = round(min(0.98, len(failed) * 0.28 + len(hard) * 0.12), 2)

            ctx.db.query(ComplianceCheck).filter(
                ComplianceCheck.email_id == email.id).delete()
            ctx.db.add(ComplianceCheck(
                tenant_id=ctx.tenant_id, email_id=email.id, verdict=verdict,
                risk_score=risk, checks=checks,
            ))
            email.status = "blocked" if verdict == "BLOCK" else "pending_approval"
            verdicts[verdict] += 1
            results.append({"email_id": email.id, "verdict": verdict,
                            "risk_score": risk,
                            "failed": [c["key"] for c in failed]})

        ctx.db.flush()
        return AgentResult(
            output={"verdicts": verdicts, "results": results},
            decision="BLOCKED_SOME" if verdicts["BLOCK"] else "APPROVE_FOR_REVIEW",
            confidence=0.94,
            reason=(f"{verdicts['APPROVE_FOR_REVIEW']} cleared, "
                    f"{verdicts['NEEDS_REVIEW']} need review, "
                    f"{verdicts['BLOCK']} blocked"),
        )

    def _run_checks(self, ctx, email, lead, window_days) -> list[dict]:
        checks: list[dict] = []

        allowed, why = policy.source_allowed(
            ctx.db, ctx.tenant_id, lead.source_connection_id if lead else None)
        checks.append({"key": "source_policy", "label": "Source policy",
                       "pass": allowed, "reason": why})

        lawful, why = policy.lawful_basis_recorded(
            ctx.db, lead.source_connection_id if lead else None)
        checks.append({"key": "lawful_basis", "label": "Lawful basis",
                       "pass": lawful, "reason": why})

        suppressed = policy.is_suppressed(ctx.db, ctx.tenant_id,
                                          lead.email if lead else "")
        checks.append({"key": "suppression", "label": "Suppression list",
                       "pass": not suppressed,
                       "reason": ("Contact is on the tenant suppression list"
                                  if suppressed else "Not suppressed")})

        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        recent = (ctx.db.query(EmailSendJob)
                  .join(GeneratedEmail, GeneratedEmail.id == EmailSendJob.email_id)
                  .filter(GeneratedEmail.lead_id == email.lead_id,
                          EmailSendJob.status == "sent",
                          EmailSendJob.created_at >= cutoff).count())
        checks.append({"key": "duplicate_contact", "label": "Duplicate contact",
                       "pass": recent == 0,
                       "reason": (f"{recent} message(s) already sent in the last "
                                  f"{window_days} days" if recent
                                  else f"No contact in the last {window_days} days")})

        body = (email.body or "").lower()
        found = [p for p in BANNED_PHRASES if p in body]
        checks.append({"key": "prohibited_claims", "label": "Prohibited claims",
                       "pass": not found,
                       "reason": (f"Unsupported claim detected: {found[0]}" if found
                                  else "No unsupported comparative claims")})

        grounded = email.groundedness >= 0.5 and len(email.body or "") > 120
        checks.append({"key": "content_quality", "label": "Content quality",
                       "pass": grounded,
                       "reason": ("Copy is grounded and within length policy" if grounded
                                  else "Copy is ungrounded or too short - no approved "
                                       "source matched")})
        return checks
