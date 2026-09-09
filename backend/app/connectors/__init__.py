"""Source connector layer.

Importing this package registers every built-in connector. Add new modules here
and they become available to the API, the workers and the portal automatically.
"""
from app.connectors.base import (  # noqa: F401
    Capability, ConfigField, ConnectorKind, FetchResult, RawLead, SourceConnector,
)
from app.connectors.registry import (  # noqa: F401
    build_connector, get_connector_class, list_connectors, register_connector,
    registry_keys,
)

# Import for side effect: each module registers itself.
from app.connectors import apollo  # noqa: F401,E402
from app.connectors import csv_url  # noqa: F401,E402
from app.connectors import hubspot  # noqa: F401,E402
from app.connectors import manual_upload  # noqa: F401,E402
from app.connectors import salesforce  # noqa: F401,E402
from app.connectors import web_profile  # noqa: F401,E402
from app.connectors import zoominfo  # noqa: F401,E402

__all__ = [
    "SourceConnector", "RawLead", "FetchResult", "ConfigField", "ConnectorKind",
    "Capability", "register_connector", "build_connector", "get_connector_class",
    "list_connectors", "registry_keys",
]
