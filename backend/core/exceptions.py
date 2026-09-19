"""API errors must be useful without exposing implementation detail."""

import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    # DRF consumes this exception, so Django's normal request logger never sees
    # it. Record only its type and source location, never the exception message
    # or request data (which may contain credentials or database parameters).
    traceback = exc.__traceback__
    while traceback and traceback.tb_next:
        traceback = traceback.tb_next
    location = "unknown"
    if traceback:
        code = traceback.tb_frame.f_code
        location = f"{code.co_filename}:{traceback.tb_lineno}"
    view = context.get("view")
    logger.error(
        "Unhandled API exception: type=%s.%s view=%s location=%s",
        type(exc).__module__,
        type(exc).__name__,
        type(view).__name__ if view is not None else "unknown",
        location,
    )
    return Response({"detail": "Unable to complete this request. Please try again."}, status=500)
