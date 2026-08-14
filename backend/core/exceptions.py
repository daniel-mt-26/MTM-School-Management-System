"""API errors must be useful without exposing implementation detail."""

from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    # Unexpected details remain server-side in normal Django logging.
    return Response({"detail": "Unable to complete this request. Please try again."}, status=500)
