from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    class Role(models.TextChoices):
        PLATFORM_ADMIN = "platform_admin", "MTM System Administrator"
        SCHOOL_ADMIN = "school_admin", "School Administrator / Receptionist"
        PARENT = "parent", "Parent / Guardian"

    role = models.CharField(max_length=20, choices=Role.choices)


class School(models.Model):
    name = models.CharField(max_length=200, unique=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to="school_logos/", blank=True)
    default_currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class SchoolAdministrator(models.Model):
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="school_administrator")
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="administrators")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.user.role != User.Role.SCHOOL_ADMIN:
            raise ValidationError({"user": "A school administrator must have the school_admin role."})


class Parent(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="parents")
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="parent_profile")
    phone_number = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.user.role != User.Role.PARENT:
            raise ValidationError({"user": "A parent profile must have the parent role."})

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class AcademicYear(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="academic_years")
    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_academic_year_per_school"),
            models.UniqueConstraint(fields=["school"], condition=Q(is_current=True), name="one_current_year_per_school"),
            models.CheckConstraint(condition=Q(end_date__gt=models.F("start_date")), name="academic_year_dates_valid"),
        ]
        indexes = [models.Index(fields=["school", "is_current"])]

    def __str__(self):
        return f"{self.school} - {self.name}"


class Term(models.Model):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="terms")
    name = models.CharField(max_length=50)
    sequence = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "name"], name="unique_term_name_per_year"),
            models.UniqueConstraint(fields=["academic_year", "sequence"], name="unique_term_sequence_per_year"),
            models.CheckConstraint(condition=Q(end_date__gt=models.F("start_date")), name="term_dates_valid"),
        ]
        ordering = ["academic_year", "sequence"]


class SchoolClass(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="classes")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="unique_class_name_per_school")]
        indexes = [models.Index(fields=["school", "is_active"])]

    def __str__(self):
        return f"{self.school} - {self.name}"


class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="students")
    admission_number = models.CharField(max_length=50)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_of_birth = models.DateField()
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="current_students")
    is_active = models.BooleanField(default=True)
    enrolled_on = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "admission_number"], name="unique_student_admission_per_school"),
        ]
        indexes = [models.Index(fields=["school_class", "is_active"]), models.Index(fields=["last_name", "first_name"])]

    def clean(self):
        if self.school_class_id and self.school_id != self.school_class.school_id:
            raise ValidationError({"school_class": "The class must belong to the student's school."})

    def __str__(self):
        return f"{self.admission_number} - {self.first_name} {self.last_name}"


class ParentStudent(models.Model):
    parent = models.ForeignKey(Parent, on_delete=models.PROTECT, related_name="student_links")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="parent_links")
    relationship = models.CharField(max_length=50, default="Guardian")
    is_primary_contact = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["parent", "student"], name="unique_parent_student_link"),
            models.UniqueConstraint(fields=["student"], condition=Q(is_primary_contact=True), name="one_primary_contact_per_student"),
        ]
        indexes = [models.Index(fields=["parent", "student"])]

    def clean(self):
        if self.parent.school_id != self.student.school_id:
            raise ValidationError("A parent and student must belong to the same school.")


class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="subjects")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_subject_name_per_school"),
            models.UniqueConstraint(fields=["school", "code"], name="unique_subject_code_per_school"),
        ]


class ClassSubject(models.Model):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="class_subjects")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="class_subjects")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="class_subjects")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school_class", "subject", "academic_year"], name="unique_class_subject_year")]

    def clean(self):
        if self.school_class.school_id != self.subject.school_id or self.school_class.school_id != self.academic_year.school_id:
            raise ValidationError("Class, subject, and academic year must belong to the same school.")


class TimetableEntry(models.Model):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="timetable_entries")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="timetable_entries")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="timetable_entries")
    day_of_week = models.CharField(max_length=20)
    start_time = models.TimeField()
    end_time = models.TimeField()
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="timetable_entries", null=True, blank=True)
    label = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "academic_year", "term", "day_of_week", "start_time", "end_time"],
                name="unique_timetable_class_period",
            ),
        ]
        indexes = [models.Index(fields=["school_class", "academic_year", "term", "day_of_week"], name="timetable_class_period_idx")]
        ordering = ["day_of_week", "start_time", "end_time"]

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError({"end_time": "End time must be after start time."})
        if self.school_class.school_id != self.academic_year.school_id:
            raise ValidationError("Class and academic year must belong to the same school.")
        if self.term.academic_year_id != self.academic_year_id:
            raise ValidationError({"term": "Term must belong to the selected academic year."})
        if self.subject_id:
            if self.subject.school_id != self.school_class.school_id:
                raise ValidationError({"subject": "Subject must belong to the class school."})
            if not ClassSubject.objects.filter(
                school_class=self.school_class,
                subject=self.subject,
                academic_year=self.academic_year,
            ).exists():
                raise ValidationError({"subject": "Subject must be assigned to this class for the selected academic year."})
        elif not self.label.strip():
            raise ValidationError({"label": "A label is required for a non-subject timetable entry."})


class StudentEnrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="enrollments")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="enrollments")
    enrolled_on = models.DateField()
    left_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(left_on__isnull=True),
                name="one_open_enrollment_per_student",
            ),
            models.CheckConstraint(
                condition=Q(left_on__isnull=True) | Q(left_on__gte=models.F("enrolled_on")),
                name="enrollment_left_on_not_before_start",
            ),
        ]
        indexes = [models.Index(fields=["school_class", "academic_year"])]

    def clean(self):
        if self.school_class.school_id != self.academic_year.school_id:
            raise ValidationError("Class and academic year must belong to the same school.")
        if self.student.school_id != self.school_class.school_id:
            raise ValidationError("A student enrollment must remain within the student's school.")
        if self.left_on and self.left_on < self.enrolled_on:
            raise ValidationError({"left_on": "The leaving date cannot be before the enrollment date."})


class Fee(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="fees")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="fees")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="fees")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="fees", null=True, blank=True)
    name = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="USD")
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    recurring_template = models.ForeignKey("RecurringFeeTemplate", on_delete=models.PROTECT, related_name="generated_fees", null=True, blank=True)
    charge_month = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["school", "academic_year", "term"])]
        constraints = [models.UniqueConstraint(fields=["recurring_template", "charge_month"], condition=Q(recurring_template__isnull=False), name="unique_recurring_fee_month")]

    def clean(self):
        if self.academic_year.school_id != self.school_id or self.term.academic_year_id != self.academic_year_id:
            raise ValidationError("Fee, academic year, and term must match the same school and year.")
        if self.currency != self.school.default_currency:
            raise ValidationError({"currency": "This school currently supports its default currency only."})
        if self.school_class_id and self.school_class.school_id != self.school_id:
            raise ValidationError({"school_class": "The class must belong to this fee's school."})


class StudentFeeAssignment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="fee_assignments")
    fee = models.ForeignKey(Fee, on_delete=models.PROTECT, related_name="student_assignments")
    amount_owed = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    currency = models.CharField(max_length=3, default="USD")
    assigned_on = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "fee"], name="unique_fee_assignment_per_student")]
        indexes = [models.Index(fields=["student", "fee"])]

    def clean(self):
        if self.student.school_class.school_id != self.fee.school_id:
            raise ValidationError("Student and fee must belong to the same school.")
        if self.currency != self.fee.currency:
            raise ValidationError({"currency": "Assignment currency must match the fee currency."})


class Payment(models.Model):
    student_fee_assignment = models.ForeignKey(StudentFeeAssignment, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="USD")
    paid_at = models.DateTimeField()
    method = models.CharField(max_length=30)
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_payments")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="reversed_payments", null=True, blank=True)
    reversal_reason = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["student_fee_assignment", "paid_at"])]


class FinancialLedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        CHARGE = "charge", "Charge"
        PAYMENT = "payment", "Payment"
        ADJUSTMENT = "adjustment", "Adjustment"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="ledger_entries")
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="USD")
    occurred_at = models.DateTimeField()
    description = models.CharField(max_length=255)
    fee_assignment = models.ForeignKey(StudentFeeAssignment, on_delete=models.PROTECT, related_name="ledger_entries", null=True, blank=True)
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="ledger_entry", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["student", "occurred_at"])]

    def clean(self):
        if self.fee_assignment_id and self.fee_assignment.student_id != self.student_id:
            raise ValidationError("The fee assignment must belong to this student.")
        if self.payment_id and self.payment.student_fee_assignment.student_id != self.student_id:
            raise ValidationError("The payment must belong to this student.")


class Receipt(models.Model):
    receipt_number = models.CharField(max_length=50, unique=True)
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="receipt")
    issued_at = models.DateTimeField()
    is_reversed = models.BooleanField(default=False)


class RecurringFeeTemplate(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="recurring_fee_templates")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="recurring_fee_templates")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="recurring_fee_templates")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="recurring_fee_templates", null=True, blank=True)
    name = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3)
    start_month = models.DateField()
    end_month = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def clean(self):
        if self.academic_year.school_id != self.school_id or self.term.academic_year_id != self.academic_year_id:
            raise ValidationError("Recurring fee template must use the school's academic year and term.")
        if self.school_class_id and self.school_class.school_id != self.school_id:
            raise ValidationError({"school_class": "The class must belong to this school."})
        if self.currency != self.school.default_currency:
            raise ValidationError({"currency": "This school currently supports its default currency only."})
        if self.end_month and self.end_month < self.start_month:
            raise ValidationError({"end_month": "End month cannot be before start month."})


class AcademicResult(models.Model):
    student_enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.PROTECT, related_name="results")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="results")
    class_subject = models.ForeignKey(ClassSubject, on_delete=models.PROTECT, related_name="results")
    score = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    maximum_score = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    comment = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_results")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student_enrollment", "term", "class_subject"], name="unique_result_per_enrollment_term_subject")]
        indexes = [models.Index(fields=["student_enrollment", "term"])]

    def clean(self):
        if self.score > self.maximum_score:
            raise ValidationError({"score": "Score cannot exceed maximum score."})
        if self.term.academic_year_id != self.student_enrollment.academic_year_id:
            raise ValidationError("Term and student enrollment must belong to the same academic year.")
        if self.class_subject.academic_year_id != self.student_enrollment.academic_year_id or self.class_subject.school_class_id != self.student_enrollment.school_class_id:
            raise ValidationError("The result's subject must be assigned to the enrolled class and year.")


class ReportCard(models.Model):
    student_enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.PROTECT, related_name="report_cards")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="report_cards")
    generated_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to="report_cards/", blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student_enrollment", "term"], name="one_report_card_per_enrollment_term")]

    def clean(self):
        if self.term.academic_year_id != self.student_enrollment.academic_year_id:
            raise ValidationError("Report-card term and enrollment must belong to the same academic year.")


class Notification(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="notifications")
    recipient = models.ForeignKey(User, on_delete=models.PROTECT, related_name="notifications", null=True, blank=True)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="notifications", null=True, blank=True)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["school", "is_read", "created_at"])]


class SchoolCommunicationSettings(models.Model):
    """Per-school controls for local communication generation, never provider credentials."""

    school = models.OneToOneField(School, on_delete=models.PROTECT, related_name="communication_settings")
    whatsapp_enabled = models.BooleanField(default=False)
    payment_receipt_notifications_enabled = models.BooleanField(default=True)
    fee_reminders_enabled = models.BooleanField(default=True)
    report_card_notifications_enabled = models.BooleanField(default=True)
    whatsapp_announcements_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class ParentCommunicationPreference(models.Model):
    class WhatsAppStatus(models.TextChoices):
        NOT_CONFIGURED = "not_configured", "Not configured"
        OPTED_IN = "opted_in", "Opted in"
        OPTED_OUT = "opted_out", "Opted out"

    parent = models.OneToOneField(Parent, on_delete=models.PROTECT, related_name="communication_preference")
    whatsapp_status = models.CharField(max_length=20, choices=WhatsAppStatus.choices, default=WhatsAppStatus.NOT_CONFIGURED)
    whatsapp_phone = models.CharField(max_length=30, blank=True)
    opted_in_at = models.DateTimeField(null=True, blank=True)
    opted_out_at = models.DateTimeField(null=True, blank=True)
    consent_source = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.whatsapp_status == self.WhatsAppStatus.OPTED_IN:
            phone = self.whatsapp_phone or self.parent.phone_number
            RegexValidator(
                regex=r"^\+[1-9]\d{7,14}$",
                message="Use an international phone number in E.164 format, for example +263771234567.",
            )(phone)
        if self.whatsapp_status == self.WhatsAppStatus.OPTED_OUT and not self.opted_out_at:
            raise ValidationError({"opted_out_at": "An opt-out timestamp is required."})


class Announcement(models.Model):
    class Audience(models.TextChoices):
        ALL_PARENTS = "all_parents", "All parents"
        SCHOOL_CLASS = "class", "Specific class"
        STUDENT = "student", "Specific student"
        PARENT = "parent", "Specific parent"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="announcements")
    title = models.CharField(max_length=200)
    message = models.TextField()
    audience = models.CharField(max_length=20, choices=Audience.choices)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="announcements", null=True, blank=True)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="announcements", null=True, blank=True)
    parent = models.ForeignKey(Parent, on_delete=models.PROTECT, related_name="announcements", null=True, blank=True)
    channels = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    recipient_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_announcements")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["school", "status", "created_at"])]

    def clean(self):
        targets = (self.school_class_id, self.student_id, self.parent_id)
        if self.audience == self.Audience.ALL_PARENTS and any(targets):
            raise ValidationError("All-parent announcements cannot have a specific audience target.")
        required = {
            self.Audience.SCHOOL_CLASS: self.school_class_id,
            self.Audience.STUDENT: self.student_id,
            self.Audience.PARENT: self.parent_id,
        }
        if self.audience in required and not required[self.audience]:
            raise ValidationError("The selected audience requires its matching target.")
        for target in (self.school_class, self.student, self.parent):
            if target and target.school_id != self.school_id:
                raise ValidationError("Announcement targets must belong to the announcement school.")


class CommunicationMessage(models.Model):
    """Durable, per-recipient delivery record. Only WhatsApp rows enter the n8n outbox."""

    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-app"
        WHATSAPP = "whatsapp", "WhatsApp"

    class EventType(models.TextChoices):
        ANNOUNCEMENT = "announcement", "Announcement"
        PAYMENT_RECEIPT = "payment_receipt", "Payment receipt"
        FEE_REMINDER = "fee_reminder", "Fee reminder"
        REPORT_CARD_AVAILABLE = "report_card_available", "Report card available"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="communication_messages")
    parent = models.ForeignKey(Parent, on_delete=models.PROTECT, related_name="communication_messages")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="communication_messages", null=True, blank=True)
    announcement = models.ForeignKey(Announcement, on_delete=models.PROTECT, related_name="messages", null=True, blank=True)
    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, related_name="communication_messages", null=True, blank=True)
    report_card = models.ForeignKey(ReportCard, on_delete=models.PROTECT, related_name="communication_messages", null=True, blank=True)
    notification = models.OneToOneField(Notification, on_delete=models.PROTECT, related_name="communication_message", null=True, blank=True)
    channel = models.CharField(max_length=12, choices=Channel.choices)
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    template_key = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    provider_message_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    attempt_count = models.PositiveIntegerField(default=0)
    claimed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["school", "status", "created_at"]),
            models.Index(fields=["channel", "status", "claimed_at"]),
            models.Index(fields=["parent", "created_at"]),
        ]

    def clean(self):
        if self.parent.school_id != self.school_id:
            raise ValidationError("A communication message parent must belong to its school.")
        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError("A communication message student must belong to its school.")


class AuditLog(models.Model):
    """Append-only, safe operational audit events; never store request bodies or secrets."""

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="audit_logs")
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="audit_logs", null=True, blank=True)
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["school", "created_at"]),
            models.Index(fields=["school", "action", "created_at"]),
        ]
