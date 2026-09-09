"""Connector registry — the single lookup used by the API and the workers."""
from app.core.errors import NotFound
from app.connectors.base import SourceConnector

_REGISTRY: dict[str, type[SourceConnector]] = {}


def register_connector(cls: type[SourceConnector]) -> type[SourceConnector]:
    """Class decorator. Registers a connector under its ``key``."""
    if not cls.key:
        raise ValueError(f"{cls.__name__} must define a key")
    _REGISTRY[cls.key] = cls
    return cls


def get_connector_class(key: str) -> type[SourceConnector]:
    if key not in _REGISTRY:
        raise NotFound(f"Unknown connector '{key}'")
    return _REGISTRY[key]


def build_connector(key: str, config: dict | None = None, tenant_id: str = "") -> SourceConnector:
    return get_connector_class(key)(config=config, tenant_id=tenant_id)


def list_connectors() -> list[dict]:
    return [cls.describe() for cls in sorted(_REGISTRY.values(), key=lambda c: c.display_name)]


def registry_keys() -> list[str]:
    return sorted(_REGISTRY)
