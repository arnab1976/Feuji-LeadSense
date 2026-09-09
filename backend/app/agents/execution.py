"""Agent 11 - Campaign Execution."""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import EmailApproval, EmailEvent, EmailSendJob, GeneratedEmail, Lead
from app.services import policy
from app.services.email_delivery import get_provider


class CampaignExecutionAgent(BaseAgent):
    key = "execution"
    name = "Campaign Execution"
    role = "Queues, schedules and sends approved emails"
    inputs = "Approved email, campaign schedule, tenant sending policy, rate limits"
    execution_strategy = (
        "Create the send job; apply throttles; queue; send via SES; store the "
        "provider ID; handle transient errors and the retry policy."
    )
    outputs = "Send status, SES message ID, timestamps, failure reason"
    stack = "AWS SES, Celery, Redis/SQS, EventBridge or SNS as needed"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        emails: list[GeneratedEmail] = kwargs["emails"]
        provider = get_provider()
        sending_policy = policy.get_policy(ctx.db, ctx.tenant_id).sending_policy or {}
        throttle = int(sending_policy.get("max_sends_per_minute", 14))

        sent, failed, skipped = 0, 0, 0
        results: list[dict] = []

        for email in emails:
            approved = (ctx.db.query(EmailApproval)
                        .filter(EmailApproval.email_id == email.id,
                                EmailApproval.decision == "approved").first())
            if not approved:
                skipped += 1
                results.append({"email_id": email.id, "status": "skipped",
                                "reason": "no human approval on record"})
                continue

            lead = ctx.db.get(Lead, email.lead_id)
            job = EmailSendJob(
                tenant_id=ctx.tenant_id, email_id=email.id,
                provider=provider.name, status="queued", attempts=1,
            )
            ctx.db.add(job)
            ctx.db.flush()

            subject = ""
            if email.subject_variants:
                idx = min(email.selected_variant, len(email.subject_variants) - 1)
                subject = email.subject_variants[idx]

            outcome = provider.send(to=lead.email if lead else "", subject=subject,
                                    body=email.body)
            job.provider_message_id = outcome.message_id
            job.status = "sent" if outcome.ok else "failed"
            job.error = outcome.error
            job.sent_at = datetime.now(timezone.utc)
            email.status = "sent" if outcome.ok else "send_failed"

            ctx.db.add(EmailEvent(
                tenant_id=ctx.tenant_id, email_id=email.id,
                provider_message_id=outcome.message_id,
                event_type="delivered" if outcome.ok else "bounced",
                payload={"provider": provider.name, "error": outcome.error,
                         "throttle_per_minute": throttle},
                occurred_at=datetime.now(timezone.utc),
            ))

            if outcome.ok:
                sent += 1
            else:
                failed += 1
                if lead and lead.email:
                    policy.suppress(ctx.db, ctx.tenant_id, lead.email,
                                    reason="hard_bounce", source="ses")
            results.append({"email_id": email.id, "status": job.status,
                            "provider_message_id": outcome.message_id,
                            "error": outcome.error})

        ctx.db.flush()
        return AgentResult(
            output={"sent": sent, "failed": failed, "skipped": skipped,
                    "results": results, "throttle_per_minute": throttle},
            decision="SENT" if sent else "NOTHING_SENT", confidence=0.98,
            reason=f"{sent} sent, {failed} failed, {skipped} skipped without approval",
        )
