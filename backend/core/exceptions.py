"""API errors must be useful without exposing implementation detail."""

import logging
import traceback

from django.db import OperationalError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def database_failure_category(exc):
    """Classify a connection error without emitting its potentially secret text."""
    if not isinstance(exc, OperationalError):
        return "not_database_operational_error"
    message = str(exc).lower()
    if any(term in message for term in ("could not translate host name", "name or service not known", "nodename nor servname", "temporary failure in name resolution")):
        return "dns_resolution"
    if any(term in message for term in ("password authentication failed", "authentication failed", "invalid authorization specification", "no pg_hba.conf entry")):
        return "authentication"
    if any(term in message for term in ("ssl", "tls", "certificate")):
        return "ssl"
    if any(term in message for term in ("timeout", "timed out")):
        return "timeout"
    if "connection refused" in message:
        return "connection_refused"
    if any(term in message for term in ("too many connections", "max client conn", "remaining connection slots", "pooler is full")):
        return "connection_limit"
    if any(term in message for term in ("connection closed", "server closed the connection", "connection reset", "broken pipe", "terminating connection")):
        return "connection_closed"
    if any(term in message for term in ("prepared statement", "unsupported startup parameter", "transaction pooling")):
        return "pooler_incompatibility"
    return "other_operational_error"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        # DRF normally serializes only ``detail``.  Preserve the safe public
        # code so clients can distinguish account states without parsing text.
        if isinstance(response.data, dict) and "detail" in response.data:
            codes = exc.get_codes() if hasattr(exc, "get_codes") else None
            code = codes if isinstance(codes, str) else None
            if code and code not in {"authentication_failed", "not_authenticated", "token_not_valid"}:
                response.data["code"] = code
        return response
    # DRF consumes this exception, so Django's request logger never sees it.
    # Log the entire call stack without exception text, source lines or locals:
    # database errors and authentication exceptions may contain secrets there.
    frames = traceback.extract_tb(exc.__traceback__)
    stack = "\n".join(
        f"  File {frame.filename}, line {frame.lineno}, in {frame.name}"
        for frame in frames
    ) or "  <traceback unavailable>"
    view = context.get("view")
    logger.error(
        "Unhandled API exception: type=%s.%s view=%s db_category=%s\nTraceback (most recent call last):\n%s",
        type(exc).__module__,
        type(exc).__name__,
        type(view).__name__ if view is not None else "unknown",
        database_failure_category(exc),
        stack,
    )
    return Response({"detail": "Unable to complete this request. Please try again."}, status=500)
