"""Private, tenant-owned intake records. No enrolment side effects."""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


def application_reference():
    return "APP-" + uuid.uuid4().hex.upper()


def enquiry_reference():
    return "ENQ-" + uuid.uuid4().hex.upper()


GRADE_CHOICES = [(g, g) for g in ["ECDA", "ECDB", *[f"Grade {i}" for i in range(1, 8)]]]


class IntakeRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey("core.School", on_delete=models.PROTECT)
    phone = models.CharField(max_length=25)
    email = models.EmailField(max_length=254)
    consent_at = models.DateTimeField()
    privacy_policy_version = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    retention_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    retention_hold = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class AdmissionApplication(IntakeRecord):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
    reference = models.CharField(max_length=36, default=application_reference, unique=True, editable=False)
    student_name = models.CharField(max_length=150)
    date_of_birth = models.DateField()
    grade = models.CharField(max_length=10, choices=GRADE_CHOICES)
    guardian_name = models.CharField(max_length=150)
    address = models.CharField(max_length=500)
    previous_school = models.CharField(max_length=150, blank=True)
    additional_information = models.CharField(max_length=2000, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="reviewed_applications")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["school", "status", "created_at"])]
        constraints = [models.CheckConstraint(condition=Q(status__in=["pending", "approved", "rejected"]), name="intake_application_status_valid")]


class ContactEnquiry(IntakeRecord):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
    reference = models.CharField(max_length=36, default=enquiry_reference, unique=True, editable=False)
    full_name = models.CharField(max_length=150)
    subject = models.CharField(max_length=200)
    message = models.CharField(max_length=3000)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    assigned_administrator = models.ForeignKey("core.SchoolAdministrator", null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_enquiries")

    class Meta:
        indexes = [models.Index(fields=["school", "status", "created_at"])]
        constraints = [models.CheckConstraint(condition=Q(status__in=["new", "in_progress", "resolved"]), name="intake_enquiry_status_valid")]


class AdmissionReviewHistory(models.Model):
    application = models.ForeignKey(AdmissionApplication, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    from_status = models.CharField(max_length=12)
    to_status = models.CharField(max_length=12)
    note = models.CharField(max_length=2000, blank=True)
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class EnquiryHandlingHistory(models.Model):
    enquiry = models.ForeignKey(ContactEnquiry, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    from_status = models.CharField(max_length=12)
    to_status = models.CharField(max_length=12)
    note = models.CharField(max_length=2000, blank=True)
    assigned_administrator = models.ForeignKey("core.SchoolAdministrator", null=True, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class PublicIntakeKey(models.Model):
    school = models.ForeignKey("core.School", on_delete=models.PROTECT)
    kind = models.CharField(max_length=12)
    key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    reference = models.CharField(max_length=36, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "kind", "key"], name="intake_public_key_unique")]


class IntakeRateBucket(models.Model):
    key = models.CharField(max_length=64, unique=True)
    hits = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class IntakeEmailOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(AdmissionApplication, null=True, blank=True, on_delete=models.CASCADE, related_name="email_jobs")
    enquiry = models.ForeignKey(ContactEnquiry, null=True, blank=True, on_delete=models.CASCADE, related_name="email_jobs")
    purpose = models.CharField(max_length=12, choices=[("school", "School notification"), ("ack", "Visitor acknowledgement")])
    recipient = models.EmailField(max_length=254)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(Q(application__isnull=False, enquiry__isnull=True) | Q(application__isnull=True, enquiry__isnull=False)), name="intake_email_one_record"),
            models.UniqueConstraint(fields=["application", "purpose"], condition=Q(application__isnull=False), name="intake_application_email_unique"),
            models.UniqueConstraint(fields=["enquiry", "purpose"], condition=Q(enquiry__isnull=False), name="intake_enquiry_email_unique"),
        ]
