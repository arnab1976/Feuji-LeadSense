"""Domain exceptions mapped to HTTP responses in app.main."""


class LeadSenseError(Exception):
    status_code = 400
    code = "leadsense_error"

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFound(LeadSenseError):
    status_code = 404
    code = "not_found"


class PermissionDenied(LeadSenseError):
    status_code = 403
    code = "permission_denied"


class PolicyViolation(LeadSenseError):
    """Raised when source policy or compliance rules block an action."""

    status_code = 409
    code = "policy_violation"


class ConnectorError(LeadSenseError):
    status_code = 502
    code = "connector_error"


class ValidationFailure(LeadSenseError):
    status_code = 422
    code = "validation_failed"
