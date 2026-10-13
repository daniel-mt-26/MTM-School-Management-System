"""Transactional intake, review history and minimal delivery jobs."""
import json
import uuid
from datetime import timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from .audit import log_action
from .models import School, SchoolAdministrator
from .intake_models import AdmissionApplication, ContactEnquiry, AdmissionReviewHistory, EnquiryHandlingHistory, PublicIntakeKey, IntakeEmailOutbox
from .intake_security import IntakeConflict, IntakeUnavailable, digest, consume_quotas, verify_challenge


def one_calendar_month_after(value):
    """Use school local time; clamp month-end to the last valid day."""
    value = timezone.localtime(value, ZoneInfo("Africa/Harare"))
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def payload_digest(data):
    return digest(json.dumps(data, sort_keys=True, separators=(",", ":"), default=str))


def confirmation(reference):
    return {"saved": True, "reference": reference, "notificationStatus": "queued", "acknowledgementStatus": "queued"}


def replay(record, payload_hash):
    if record.payload_hash != payload_hash:
        raise IntakeConflict()
    if not record.reference:
        raise IntakeUnavailable()
    return confirmation(record.reference)


def submit(kind, school, operation_id, values):
    values = dict(values)
    token = values.pop("challengeToken", "")
    values.pop("website", "")
    values.pop("consent", None)
    hashed = payload_digest(values)
    existing = PublicIntakeKey.objects.filter(school=school, kind=kind, key=operation_id).first()
    if existing:
        return replay(existing, hashed), False
    verify_challenge(token, uuid.uuid5(uuid.NAMESPACE_URL, f"{school.pk}:{kind}:{operation_id}"))
    now = timezone.now()
    with transaction.atomic():
        locked_school = School.objects.select_for_update().get(pk=school.pk)
        if not locked_school.is_operational or locked_school.is_demo:
            raise IntakeUnavailable()
        key, created = PublicIntakeKey.objects.get_or_create(school=school, kind=kind, key=operation_id, defaults={"payload_hash": hashed, "expires_at": now + timedelta(days=settings.MTM_INTAKE_KEY_RETENTION_DAYS)})
        if not created:
            return replay(key, hashed), False
        consume_quotas([("recipient", f"{school.pk}:{values['email'].casefold()}", settings.MTM_INTAKE_RECIPIENT_LIMIT, 86400)])
        model = AdmissionApplication if kind == "application" else ContactEnquiry
        record = model.objects.create(school=locked_school, consent_at=now, retention_expires_at=None, **values)
        relation = {"application": record} if kind == "application" else {"enquiry": record}
        for purpose, recipient in [("school", settings.MTM_INTAKE_SCHOOL_EMAIL), ("ack", record.email)]:
            IntakeEmailOutbox.objects.create(**relation, purpose=purpose, recipient=recipient, next_attempt_at=now)
        log_action(school=locked_school, actor=None, action=f"intake.{kind}.submitted", resource=record)
        key.reference = record.reference
        key.save(update_fields=["reference"])
        return confirmation(record.reference), True


def review(kind, school, actor, pk, values):
    model = AdmissionApplication if kind == "application" else ContactEnquiry
    with transaction.atomic():
        locked_school = School.objects.select_for_update().get(pk=school.pk)
        if not locked_school.is_operational:
            raise IntakeUnavailable()
        if not SchoolAdministrator.objects.filter(school=locked_school, user=actor, user__is_active=True, user__role="school_admin", user__must_change_password=False).exists():
            raise PermissionDenied()
        record = model.objects.select_for_update().filter(pk=pk, school=locked_school).first()
        if record is None:
            raise NotFound()
        if record.version != values["version"]:
            raise IntakeConflict("This record changed. Reload it before reviewing.")
        assigned = None
        if "assignedAdministratorId" in values:
            ident = values["assignedAdministratorId"]
            if ident is not None:
                assigned = SchoolAdministrator.objects.filter(pk=ident, school=school, user__is_active=True, user__role="school_admin").first()
                if assigned is None:
                    raise ValidationError({"assignedAdministratorId": "Select an administrator from your school."})
            record.assigned_administrator = assigned
        old_status = record.status
        record.status = values.get("status", record.status)
        terminal = "rejected" if kind == "application" else "resolved"
        if record.status != terminal:
            record.retention_expires_at = None
        elif old_status != record.status:
            record.retention_expires_at = one_calendar_month_after(timezone.now())
        # Notes and assignments do not restart a completed decision clock.
        record.version += 1
        if kind == "application":
            record.reviewer = actor
            record.reviewed_at = timezone.now()
        record.save()
        history = {"actor": actor, "from_status": old_status, "to_status": record.status, "note": values.get("note", ""), "version": record.version}
        if kind == "application":
            AdmissionReviewHistory.objects.create(application=record, **history)
        else:
            EnquiryHandlingHistory.objects.create(enquiry=record, assigned_administrator=record.assigned_administrator, **history)
        log_action(school=locked_school, actor=actor, action=f"intake.{kind}.reviewed", resource=record, description=f"{old_status} -> {record.status}; version {record.version}")
        return record
