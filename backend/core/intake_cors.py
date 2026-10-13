"""Allow approved brochure origins only on the two anonymous intake routes."""
from django.conf import settings
from django.dispatch import receiver
from corsheaders.signals import check_request_enabled


@receiver(check_request_enabled, dispatch_uid="mtm.intake.cors")
def public_intake_cors(sender, request, **kwargs):
    return request.path in {"/api/public/beavers/applications/", "/api/public/beavers/enquiries/"} and request.method in {"POST", "OPTIONS"} and request.headers.get("Origin") in settings.MTM_INTAKE_ALLOWED_ORIGINS
