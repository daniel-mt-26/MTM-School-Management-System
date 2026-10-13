"""Fail-closed publication gate, bounded JSON and shared PostgreSQL quotas."""
import ipaddress
import hashlib
import hmac
import json
from datetime import timedelta
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ParseError, Throttled, ValidationError
from rest_framework.parsers import BaseParser
from .intake_models import IntakeRateBucket
from .models import School


class IntakeUnavailable(APIException):
    status_code = 503
    default_detail = "Online submissions are temporarily unavailable."
    default_code = "intake_unavailable"


class IntakeConflict(APIException):
    status_code = 409
    default_detail = "This operation conflicts with an earlier request."
    default_code = "intake_conflict"


class IntakeTooLarge(APIException):
    status_code = 413
    default_detail = "This submission is too large."


def reject_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


class BoundedJSONParser(BaseParser):
    media_type = "application/json"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read(settings.MTM_INTAKE_MAX_BYTES + 1)
        if len(raw) > settings.MTM_INTAKE_MAX_BYTES:
            raise IntakeTooLarge()
        try:
            return json.loads(raw, object_pairs_hook=reject_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            raise ParseError("Provide a valid JSON object without duplicate fields.")


def digest(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def public_school(request):
    if not (settings.MTM_INTAKE_ENABLED and settings.MTM_INTAKE_PRIVACY_APPROVED and settings.MTM_INTAKE_PRIVACY_VERSION and settings.MTM_INTAKE_BEAVERS_SCHOOL_ID and settings.MTM_INTAKE_KEY_RETENTION_DAYS > 0):
        raise IntakeUnavailable()
    if request.query_params:
        raise ValidationError({"detail": "Query parameters are not accepted."})
    if settings.IS_PRODUCTION:
        if connection.vendor != "postgresql" or any(urlparse(origin).scheme != "https" for origin in settings.MTM_INTAKE_ALLOWED_ORIGINS):
            raise IntakeUnavailable()
        if not request.is_secure() or not settings.MTM_INTAKE_ALLOWED_ORIGINS or not settings.MTM_INTAKE_CHALLENGE_SECRET or not settings.MTM_INTAKE_CHALLENGE_REQUIRED:
            raise IntakeUnavailable()
    origin = request.headers.get("Origin")
    if origin and origin not in settings.MTM_INTAKE_ALLOWED_ORIGINS:
        raise ValidationError({"detail": "This origin is not permitted."})
    if not settings.MTM_INTAKE_ALLOWED_ORIGINS:
        raise IntakeUnavailable()
    if settings.MTM_INTAKE_CHALLENGE_REQUIRED and not settings.MTM_INTAKE_CHALLENGE_SECRET:
        raise IntakeUnavailable()
    length = request.META.get("CONTENT_LENGTH", "")
    if length:
        try:
            if int(length) > settings.MTM_INTAKE_MAX_BYTES:
                raise IntakeTooLarge()
        except ValueError:
            raise ParseError("Invalid request size.")
    school = School.objects.filter(pk=settings.MTM_INTAKE_BEAVERS_SCHOOL_ID, is_active=True, status=School.Status.ACTIVE, is_demo=False).first()
    if school is None:
        raise IntakeUnavailable()
    return school


def client_ip(request):
    # Forwarding headers are trusted only through explicitly configured proxy CIDRs.
    raw = request.META.get("REMOTE_ADDR", "")
    try:
        current = ipaddress.ip_address(raw)
        networks = [ipaddress.ip_network(cidr) for cidr in settings.MTM_INTAKE_TRUSTED_PROXY_CIDRS]
    except ValueError:
        return "unknown"
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not networks or not any(current in net for net in networks) or len(forwarded) > 512:
        return str(current)
    try:
        hops = [ipaddress.ip_address(value.strip()) for value in forwarded.split(",") if value.strip()]
    except ValueError:
        return str(current)
    if len(hops) > 16:
        return str(current)
    for hop in reversed(hops):
        if not any(current in net for net in networks):
            break
        current = hop
    return str(current)


def consume_quotas(entries):
    now = timezone.now()
    buckets = []
    for scope, value, limit, seconds in entries:
        if limit <= 0:
            raise IntakeUnavailable()
        window = int(now.timestamp()) // seconds
        key = digest(f"{scope}:{value}:{window}")
        buckets.append((key, limit, seconds))
    with transaction.atomic():
        rows = []
        for key, limit, seconds in sorted(buckets):
            IntakeRateBucket.objects.get_or_create(key=key, defaults={"expires_at": now + timedelta(seconds=seconds * 2)})
            row = IntakeRateBucket.objects.select_for_update().get(key=key)
            if row.hits >= limit:
                raise Throttled(wait=seconds, detail="Too many submissions. Please try again later.")
            rows.append(row)
        for row in rows:
            row.hits += 1
            row.save(update_fields=["hits"])


def verify_challenge(token, operation_id):
    if not settings.MTM_INTAKE_CHALLENGE_REQUIRED:
        return
    if not token:
        raise ValidationError({"challengeToken": "Complete the verification challenge."})
    body = urlencode({"secret": settings.MTM_INTAKE_CHALLENGE_SECRET, "response": token, "idempotency_key": str(operation_id)}).encode()
    try:
        req = Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read(8192))
    except Exception:
        raise IntakeUnavailable() from None
    hosts = {urlparse(origin).hostname for origin in settings.MTM_INTAKE_ALLOWED_ORIGINS}
    if not isinstance(data, dict) or data.get("success") is not True or data.get("hostname") not in hosts or data.get("action") != "beavers_intake":
        raise ValidationError({"challengeToken": "Verification failed. Please try again."})
