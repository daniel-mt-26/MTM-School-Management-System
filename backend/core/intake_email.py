"""Existing PostgreSQL outbox: leased delivery, minimal templates and safe failures."""
import smtplib
import ssl
import uuid
from datetime import timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.mail import EmailMessage, mailers
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from .intake_models import IntakeEmailOutbox
from .models import School
from .audit import log_action

TERMINAL_FAILURES = ("smtp_permanent", "smtp_configuration", "recipient_invalid", "recipient_mismatch", "message_invalid", "retention_expired", "delivery_uncertain")


def valid_address(value):
    if not isinstance(value, str) or len(value) > 254 or any(c in value for c in "\r\n"):
        return False
    try:
        validate_email(value)
    except ValidationError:
        return False
    return not value.casefold().endswith("@localhost")


def dashboard_origin():
    value = settings.MTM_INTAKE_DASHBOARD_URL.strip()
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/") or any(c.isspace() for c in value)):
            return None
        url.port  # Reject malformed ports without logging the supplied value.
    except ValueError:
        return None
    return value.rstrip("/")


def smtp_ready():
    mailer = settings.MAILERS.get("default", {})
    options = mailer.get("OPTIONS", {})
    timeout = options.get("timeout")
    tls, ssl = bool(options.get("use_tls")), bool(options.get("use_ssl"))
    if not (settings.MTM_INTAKE_EMAIL_ENABLED and settings.MTM_INTAKE_SMTP_VERIFIED and mailer.get("BACKEND") == "django.core.mail.backends.smtp.EmailBackend" and options.get("host") and options.get("username") and options.get("password") and tls != ssl):
        return False
    if not (isinstance(timeout, (int, float)) and 1 <= timeout <= 30 and settings.MTM_INTAKE_EMAIL_LEASE_SECONDS >= 10 * timeout and settings.MTM_INTAKE_EMAIL_MAX_ATTEMPTS > 0):
        return False
    if not all(valid_address(value) for value in (settings.DEFAULT_FROM_EMAIL, settings.MTM_INTAKE_SCHOOL_EMAIL, settings.MTM_INTAKE_CONTACT_EMAIL)):
        return False
    if not dashboard_origin() or not settings.MTM_INTAKE_CONTACT_PHONES.strip():
        return False
    return School.objects.filter(pk=settings.MTM_INTAKE_BEAVERS_SCHOOL_ID, is_active=True, status=School.Status.ACTIVE, is_demo=False).exists()


def claim_job():
    now = timezone.now()
    expired = now - timedelta(seconds=settings.MTM_INTAKE_EMAIL_LEASE_SECONDS)
    with transaction.atomic():
        rows = (IntakeEmailOutbox.objects.select_for_update(skip_locked=True, of=("self",))
                .filter(Q(application__school_id=settings.MTM_INTAKE_BEAVERS_SCHOOL_ID) | Q(enquiry__school_id=settings.MTM_INTAKE_BEAVERS_SCHOOL_ID))
                .filter(attempts__lt=settings.MTM_INTAKE_EMAIL_MAX_ATTEMPTS)
                .exclude(failure_code__in=TERMINAL_FAILURES)
                .filter(Q(application__retention_expires_at__gt=now) | Q(enquiry__retention_expires_at__gt=now) | Q(application__isnull=False, application__retention_expires_at__isnull=True) | Q(enquiry__isnull=False, enquiry__retention_expires_at__isnull=True))
                .filter(Q(status__in=["pending", "failed"], next_attempt_at__lte=now) | Q(status="sending", claimed_at__lt=expired))
                .order_by("created_at", "id"))
        job = rows.first()
        if job is None:
            return None
        job.status = "sending"
        job.claimed_at = now
        job.claim_token = uuid.uuid4()
        job.attempts += 1
        job.save(update_fields=["status", "claimed_at", "claim_token", "attempts"])
        return job


def build_message(job, record):
    if not valid_address(job.recipient):
        raise ValidationError("Invalid recipient")
    application = bool(job.application_id)
    kind = "application" if application else "enquiry"
    if job.purpose not in ("school", "ack"):
        raise ValidationError("Invalid message purpose")
    # Deliberate allowlist: never supply the record or its private fields to templates.
    context = {"school_name": "Beavers Junior School", "reference": record.reference,
               "school_contact_email": settings.MTM_INTAKE_CONTACT_EMAIL,
               "school_contact_phones": settings.MTM_INTAKE_CONTACT_PHONES}
    if job.purpose == "school":
        context.update(submitted_at=timezone.localtime(record.created_at, ZoneInfo("Africa/Harare")).strftime("%d %B %Y at %H:%M CAT"),
                       dashboard_url=f"{dashboard_origin()}/school/{'admissions' if application else 'enquiries'}/{record.pk}")
        if application:
            context["grade"] = record.grade
    template = f"intake/{kind}_{job.purpose}"
    subject = render_to_string(f"{template}.subject.txt", context).strip()
    if any(c in subject for c in "\r\n"):
        raise ValidationError("Invalid subject")
    return EmailMessage(subject=subject, body=render_to_string(f"{template}.txt", context),
                        from_email=settings.DEFAULT_FROM_EMAIL, to=[job.recipient], reply_to=[settings.MTM_INTAKE_CONTACT_EMAIL],
                        headers={"Message-ID": f"<intake-{job.pk}@mtm-sms.co.zw>"})


def failure_code(error):
    if isinstance(error, (smtplib.SMTPNotSupportedError, ssl.SSLCertVerificationError)):
        return "smtp_configuration"
    if isinstance(error, (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused)):
        return "smtp_temporary" if 400 <= error.smtp_code < 500 else "smtp_configuration"
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        codes = [value[0] for value in error.recipients.values()]
        return "smtp_permanent" if codes and all(500 <= code < 600 for code in codes) else "smtp_temporary"
    if isinstance(error, smtplib.SMTPResponseException):
        return "smtp_permanent" if 500 <= error.smtp_code < 600 else "smtp_temporary"
    return "provider_error"


def finish_job(job, record, code=""):
    now = timezone.now()
    with transaction.atomic():
        changed = IntakeEmailOutbox.objects.filter(pk=job.pk, status="sending", claim_token=job.claim_token).update(
            status="failed" if code else "sent", sent_at=None if code else now, failure_code=code,
            next_attempt_at=now + timedelta(seconds=min(3600, 60 * 2 ** min(job.attempts, 6))))
        if changed:
            log_action(school=record.school, actor=None, action="intake.email.failed" if code else "intake.email.sent", resource=job,
                       description=f"purpose={job.purpose}; attempt={job.attempts}; outcome={code or 'smtp_accepted'}")
        return changed


def recover_exhausted_jobs(limit):
    """A final crashed lease is uncertain, not a fabricated successful delivery."""
    expired = timezone.now() - timedelta(seconds=settings.MTM_INTAKE_EMAIL_LEASE_SECONDS)
    changed = 0
    with transaction.atomic():
        rows = (IntakeEmailOutbox.objects.select_for_update(skip_locked=True, of=("self",))
                .filter(Q(application__school_id=settings.MTM_INTAKE_BEAVERS_SCHOOL_ID) | Q(enquiry__school_id=settings.MTM_INTAKE_BEAVERS_SCHOOL_ID))
                .filter(status="sending", attempts__gte=settings.MTM_INTAKE_EMAIL_MAX_ATTEMPTS, claimed_at__lt=expired)
                .order_by("created_at", "id")[:limit])
        for job in rows:
            record = job.application if job.application_id else job.enquiry
            if finish_job(job, record, "delivery_uncertain"):
                changed += 1
    return changed


def process_email(limit=100):
    if not smtp_ready():
        return {"enabled": False, "sent": 0, "failed": 0}
    counts = {"enabled": True, "sent": 0, "failed": 0}
    counts["failed"] = recover_exhausted_jobs(limit)
    for _ in range(limit):
        job = claim_job()
        if job is None:
            break
        try:
            record = job.application if job.application_id else job.enquiry
        except ObjectDoesNotExist:
            continue  # Cascading deletion removes the job, too.
        code = ""
        if record.retention_expires_at is not None and record.retention_expires_at <= timezone.now():
            code = "retention_expired"
        elif not valid_address(job.recipient):
            code = "recipient_invalid"
        elif job.recipient.casefold() != (settings.MTM_INTAKE_SCHOOL_EMAIL if job.purpose == "school" else record.email).casefold():
            code = "recipient_mismatch"
        else:
            try:
                message = build_message(job, record)
                # Django 6.1 MAILERS API; explicit backend=get_connection is incompatible.
                sent = mailers.default.send_messages([message])
                if sent != 1:
                    code = "provider_error"
            except ValidationError:
                code = "message_invalid"
            except Exception as error:
                # Never record provider text, recipients, bodies or credentials.
                code = failure_code(error)
        changed = finish_job(job, record, code)
        if changed:
            counts["failed" if code else "sent"] += 1
        if code == "smtp_configuration":
            break  # Do not exhaust every queued job with broken sender/authentication.
    return counts
