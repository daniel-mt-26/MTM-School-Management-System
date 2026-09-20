"""API errors must be useful without exposing implementation detail."""

import logging
import traceback

from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
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
        "Unhandled API exception: type=%s.%s view=%s\nTraceback (most recent call last):\n%s",
        type(exc).__module__,
        type(exc).__name__,
        type(view).__name__ if view is not None else "unknown",
        stack,
    )
    return Response({"detail": "Unable to complete this request. Please try again."}, status=500)
