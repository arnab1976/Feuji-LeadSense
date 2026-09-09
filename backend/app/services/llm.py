"""LLM gateway with provider abstraction.

The rest of the codebase calls ``llm.complete(...)`` and never imports a vendor
SDK. Swapping Claude for Azure OpenAI is an environment variable, not a rewrite.

The ``echo`` provider is a deterministic local generator. It produces
well-formed, sensible output without a network call, so the whole agent pipeline
runs in CI and on a laptop with no API key.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("leadsense.llm")

# Rough per-1k-token prices used for cost telemetry in the demo.
PRICE_PER_1K = {"input": 0.003, "output": 0.015}


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        return round(
            self.input_tokens / 1000 * PRICE_PER_1K["input"]
            + self.output_tokens / 1000 * PRICE_PER_1K["output"],
            6,
        )

    def json(self) -> Any:
        """Parse a JSON body, tolerating code fences around it."""
        cleaned = re.sub(r"^```(?:json)?|```$", "", self.text.strip(), flags=re.MULTILINE)
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            match = re.search(r"[\{\[].*[\}\]]", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise


class BaseProvider:
    name = "base"

    def complete(self, system: str, prompt: str, max_tokens: int, temperature: float) -> LLMResponse:
        raise NotImplementedError


class EchoProvider(BaseProvider):
    """Deterministic offline generator used when LLM_PROVIDER=echo.

    It understands the small set of structured requests the agents make and
    returns valid JSON for each, so downstream parsing behaves exactly as it will
    against a hosted model.
    """

    name = "echo"

    def complete(self, system, prompt, max_tokens, temperature) -> LLMResponse:
        text = self._route(prompt)
        return LLMResponse(
            text=text, model="echo-local",
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
            raw={"provider": "echo"},
        )

    def _route(self, prompt: str) -> str:
        lowered = prompt.lower()
        if "campaign_brief" in lowered or "campaign brief" in lowered:
            return json.dumps(self._campaign_brief(prompt))
        if "subject_variants" in lowered or "write an outreach email" in lowered:
            return json.dumps(self._email(prompt))
        if "classify the reply" in lowered or "reply_intent" in lowered:
            return json.dumps(self._reply(prompt))
        if "segment_label" in lowered:
            return json.dumps({"label": "Operations leaders",
                               "rationale": "Shared function and seniority band"})
        return json.dumps({"result": "ok", "note": "echo provider default response"})

    @staticmethod
    def _field(prompt: str, key: str, default: str = "") -> str:
        match = re.search(rf"{key}:\s*(.+)", prompt)
        return match.group(1).strip() if match else default

    def _campaign_brief(self, prompt: str) -> dict:
        segment = self._field(prompt, "Segment", "the target segment")
        objective = self._field(prompt, "Objective", "book discovery calls")
        return {
            "audience": f"{segment} contacts who own prospect data quality",
            "pain": ("Sales teams work from prospect records nobody trusts, so outreach "
                     "lands on stale titles and the wrong accounts."),
            "value_proposition": ("Verified, enriched and scored lead records with an "
                                  "auditable trail from source to send."),
            "messaging_themes": [
                "Data you can defend in a pipeline review",
                "Verification before personalisation",
                "Governed automation, not unattended sending",
            ],
            "objective_restated": objective,
            "sequence": [
                {"day": 0, "step": "Opening email",
                 "goal": "Name the specific data problem and offer one proof point"},
                {"day": 3, "step": "Value follow-up",
                 "goal": "Share the case study outcome and ask one qualifying question"},
                {"day": 8, "step": "Perspective email",
                 "goal": "Benchmark their segment against peer data, with no ask"},
                {"day": 14, "step": "Breakup or handoff",
                 "goal": "Close the loop or route to a human sales owner"},
            ],
        }

    def _email(self, prompt: str) -> dict:
        name = self._field(prompt, "Lead name", "there")
        first = name.split(" ")[0]
        company = self._field(prompt, "Company", "your team")
        title = self._field(prompt, "Title", "your role")
        evidence = self._field(prompt, "Approved evidence", "")
        proof = (f"\n\nFor context, {evidence}\n" if evidence
                 else "\n\nWe can share the underlying benchmark once your team has "
                      "approved the source material.\n")
        body = (
            f"Hi {first},\n\n"
            f"I have been looking at how {company} moves prospect data through its "
            f"sales motion, and I suspect you hit the same wall most people in "
            f"{title.lower()} roles do.\n\n"
            "We built LeadSense because the expensive part of outbound is not writing "
            "the email, it is trusting the record behind it. Every lead is reconciled "
            "against its source, given a status a reviewer can challenge, and scored on "
            "factors you can see."
            f"{proof}\n"
            "Worth a short call to see whether the same pattern shows up in your numbers?"
        )
        return {
            "subject_variants": [
                f"{company} - verifying prospect data before it reaches your team",
                f"A question about how {company} verifies its contact records",
            ],
            "body": body,
            "cta": "Book a 20-minute discovery call",
        }

    def _reply(self, prompt: str) -> dict:
        text = prompt.lower()
        if any(w in text for w in ["remove me", "unsubscribe", "do not contact"]):
            return {"intent": "UNSUBSCRIBE", "confidence": 0.99, "score_delta": -40,
                    "next_action": "Add to the suppression list, stop all sequences and "
                                   "record the request",
                    "requires_human": False}
        if any(w in text for w in ["thursday", "call", "meeting", "calendar", "schedule"]):
            return {"intent": "MEETING_REQUEST", "confidence": 0.95, "score_delta": 12,
                    "next_action": "Notify the account owner, create a CRM task and stop "
                                   "the automated sequence",
                    "requires_human": True}
        if any(w in text for w in ["send", "more information", "details", "how does"]):
            return {"intent": "INFORMATION_REQUEST", "confidence": 0.88, "score_delta": 6,
                    "next_action": "Send the approved technical brief and hold the "
                                   "sequence for seven days",
                    "requires_human": False}
        if any(w in text for w in ["budget", "next year", "not a priority", "later"]):
            return {"intent": "NOT_NOW", "confidence": 0.9, "score_delta": -3,
                    "next_action": "Move to the nurture track and suppress outbound for "
                                   "ninety days",
                    "requires_human": False}
        if any(w in text for w in ["moved to", "no longer", "copying", "owns this"]):
            return {"intent": "REFERRAL", "confidence": 0.86, "score_delta": 4,
                    "next_action": "Create the referred contact, re-verify the original "
                                   "record and route the sequence to the new owner",
                    "requires_human": True}
        return {"intent": "UNCLEAR", "confidence": 0.4, "score_delta": 0,
                "next_action": "Route to a human for reading", "requires_human": True}


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def complete(self, system, prompt, max_tokens, temperature) -> LLMResponse:
        with httpx.Client(timeout=90) as client:
            resp = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        usage = data.get("usage", {})
        return LLMResponse(text=text, model=data.get("model", settings.llm_model),
                           input_tokens=usage.get("input_tokens", 0),
                           output_tokens=usage.get("output_tokens", 0), raw=data)


class OpenAIProvider(BaseProvider):
    name = "openai"

    def complete(self, system, prompt, max_tokens, temperature) -> LLMResponse:
        with httpx.Client(timeout=90) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.llm_model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            model=data.get("model", settings.llm_model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0), raw=data,
        )


class AzureOpenAIProvider(OpenAIProvider):
    name = "azure_openai"

    def complete(self, system, prompt, max_tokens, temperature) -> LLMResponse:
        url = (f"{settings.azure_openai_endpoint}/openai/deployments/"
               f"{settings.azure_openai_deployment}/chat/completions"
               "?api-version=2024-06-01")
        with httpx.Client(timeout=90) as client:
            resp = client.post(
                url, headers={"api-key": settings.azure_openai_api_key},
                json={
                    "max_tokens": max_tokens, "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            model=settings.azure_openai_deployment,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0), raw=data,
        )


_PROVIDERS = {
    "echo": EchoProvider, "anthropic": AnthropicProvider,
    "openai": OpenAIProvider, "azure_openai": AzureOpenAIProvider,
}


class LLMGateway:
    def __init__(self, provider: str | None = None):
        key = provider or settings.llm_provider
        self.provider: BaseProvider = _PROVIDERS.get(key, EchoProvider)()

    def complete(self, prompt: str, system: str = "You are a precise assistant.",
                 max_tokens: int = 1200, temperature: float = 0.3) -> LLMResponse:
        try:
            return self.provider.complete(system, prompt, max_tokens, temperature)
        except Exception as exc:
            log.warning("LLM provider %s failed (%s); falling back to echo",
                        self.provider.name, exc)
            return EchoProvider().complete(system, prompt, max_tokens, temperature)


llm = LLMGateway()
