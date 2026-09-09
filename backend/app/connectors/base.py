"""Source connector contract.

Every lead source in LeadSense — a spreadsheet a rep drags in, a Salesforce
report, a HubSpot list, an Apollo search — is a subclass of ``SourceConnector``.
The rest of the platform never talks to a vendor SDK directly; it talks to this
interface, which is why adding a source is a single new file plus a registry
entry.

Adding your own connector
-------------------------
1. Create ``app/connectors/<yours>.py``.
2. Subclass ``SourceConnector``, set ``key`` / ``display_name`` / ``kind``.
3. Declare ``config_fields`` so the portal can render its settings form.
4. Implement ``test_connection`` and ``fetch``. Implement ``push`` too if the
   source supports write-back.
5. Import it in ``app/connectors/__init__.py``.

Nothing else in the codebase needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from app.core.config import settings
from app.core.errors import ConnectorError


class ConnectorKind(str, Enum):
    FILE = "file"          # user-supplied files
    CRM = "crm"            # bidirectional systems of record
    ENRICHMENT = "enrichment"  # prospecting and data vendors
    WEB = "web"            # policy-gated public sources
    INTERNAL = "internal"  # demo and test fixtures


class Capability(str, Enum):
    FETCH = "fetch"                # read leads in
    PUSH = "push"                  # write leads or activity back
    INCREMENTAL = "incremental"    # supports a sync cursor
    SEARCH = "search"              # supports server-side query filters
    ENRICH = "enrich"              # can enrich a single known record
    WEBHOOK = "webhook"            # can deliver change events


@dataclass
class ConfigField:
    """One field in a connector's settings form, rendered by the portal."""

    name: str
    label: str
    type: str = "text"          # text | password | number | boolean | select | file
    required: bool = False
    help: str = ""
    default: Any = None
    options: list[str] = field(default_factory=list)
    secret: bool = False


@dataclass
class RawLead:
    """The single shape every connector must produce.

    ``raw`` keeps the untouched vendor payload so nothing is lost and mappings can
    be re-run later without re-fetching.
    """

    external_id: str = ""
    full_name: str = ""
    email: str = ""
    title: str = ""
    company_name: str = ""
    location: str = ""
    profile_url: str = ""
    phone: str = ""
    industry: str = ""
    employee_count: int = 0
    tech_stack: list[str] = field(default_factory=list)
    source: str = ""
    raw: dict = field(default_factory=dict)

    def dedupe_key(self) -> str:
        if self.email:
            return self.email.strip().lower()
        return f"{self.full_name.strip().lower()}|{self.company_name.strip().lower()}"

    def is_valid(self) -> tuple[bool, str]:
        if not self.full_name and not self.email:
            return False, "record has neither a name nor an email address"
        if self.email and ("@" not in self.email or "." not in self.email.split("@")[-1]):
            return False, f"malformed email address: {self.email}"
        return True, ""


@dataclass
class FetchResult:
    leads: list[RawLead]
    cursor: str = ""
    has_more: bool = False
    warnings: list[str] = field(default_factory=list)


class SourceConnector(ABC):
    """Base class for every lead source."""

    key: str = ""
    display_name: str = ""
    description: str = ""
    kind: ConnectorKind = ConnectorKind.INTERNAL
    capabilities: set[Capability] = {Capability.FETCH}
    config_fields: list[ConfigField] = []
    #: Sources whose terms of service or lawful basis need review before use.
    requires_policy_review: bool = False

    def __init__(self, config: dict | None = None, tenant_id: str = ""):
        self.config = config or {}
        self.tenant_id = tenant_id

    # -- helpers ---------------------------------------------------------
    def setting(self, name: str, env_default: str = "") -> Any:
        """Read a config value, falling back to the environment default."""
        value = self.config.get(name)
        if value in (None, ""):
            value = getattr(settings, env_default, "") if env_default else ""
        return value

    @property
    def demo_mode(self) -> bool:
        """True when no credentials are configured and demo data is allowed.

        This is what lets a fresh clone run the entire pipeline offline.
        """
        return settings.demo_connectors and not self.has_credentials()

    def has_credentials(self) -> bool:
        return True

    # -- contract --------------------------------------------------------
    @abstractmethod
    def test_connection(self) -> dict:
        """Return ``{"ok": bool, "message": str, "details": {...}}``."""

    @abstractmethod
    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        """Pull a page of leads from the source."""

    def push(self, records: Iterable[dict]) -> dict:
        """Write records or activity back to the source."""
        raise ConnectorError(f"{self.display_name} does not support write-back")

    def enrich(self, lead: dict) -> dict:
        """Return additional attributes for a single known record."""
        raise ConnectorError(f"{self.display_name} does not support enrichment")

    # -- introspection ---------------------------------------------------
    @classmethod
    def describe(cls) -> dict:
        return {
            "key": cls.key,
            "display_name": cls.display_name,
            "description": cls.description,
            "kind": cls.kind.value,
            "capabilities": sorted(c.value for c in cls.capabilities),
            "requires_policy_review": cls.requires_policy_review,
            "config_fields": [
                {
                    "name": f.name, "label": f.label, "type": f.type,
                    "required": f.required, "help": f.help, "default": f.default,
                    "options": f.options, "secret": f.secret,
                }
                for f in cls.config_fields
            ],
        }
