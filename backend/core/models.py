from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
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
    is_active = models.BooleanField(default=True)
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
    admission_number = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_of_birth = models.DateField()
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="current_students")
    is_active = models.BooleanField(default=True)
    enrolled_on = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["school_class", "is_active"]), models.Index(fields=["last_name", "first_name"])]

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


class StudentEnrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="enrollments")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="enrollments")
    enrolled_on = models.DateField()
    left_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "academic_year"], name="one_enrollment_per_student_per_year")]
        indexes = [models.Index(fields=["school_class", "academic_year"])]

    def clean(self):
        if self.school_class.school_id != self.academic_year.school_id:
            raise ValidationError("Class and academic year must belong to the same school.")
        if self.student.school_class.school_id != self.school_class.school_id:
            raise ValidationError("A student enrollment must remain within the student's school.")


class Fee(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="fees")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="fees")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="fees")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="fees", null=True, blank=True)
    name = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["school", "academic_year", "term"])]

    def clean(self):
        if self.academic_year.school_id != self.school_id or self.term.academic_year_id != self.academic_year_id:
            raise ValidationError("Fee, academic year, and term must match the same school and year.")
        if self.school_class_id and self.school_class.school_id != self.school_id:
            raise ValidationError({"school_class": "The class must belong to this fee's school."})


class StudentFeeAssignment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="fee_assignments")
    fee = models.ForeignKey(Fee, on_delete=models.PROTECT, related_name="student_assignments")
    amount_owed = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    assigned_on = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "fee"], name="unique_fee_assignment_per_student")]
        indexes = [models.Index(fields=["student", "fee"])]

    def clean(self):
        if self.student.school_class.school_id != self.fee.school_id:
            raise ValidationError("Student and fee must belong to the same school.")


class Payment(models.Model):
    student_fee_assignment = models.ForeignKey(StudentFeeAssignment, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    paid_at = models.DateTimeField()
    method = models.CharField(max_length=30)
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_payments")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["school", "is_read", "created_at"])]
