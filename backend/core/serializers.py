from copy import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    AcademicResult,
    AcademicYear,
    ClassSubject,
    Fee,
    FinancialLedgerEntry,
    Notification,
    ParentStudent,
    Payment,
    Receipt,
    ReportCard,
    School,
    SchoolClass,
    Student,
    StudentEnrollment,
    StudentFeeAssignment,
    Subject,
    Term,
    User,
)


class SchoolScopedSerializerMixin:
    """Limits submitted related-object IDs to the current administrator's school."""

    scoped_related_fields = {}

    def get_school(self):
        try:
            return self.context["school"]
        except KeyError as exc:
            raise AssertionError("School-scoped serializers require a school context.") from exc

    def get_fields(self):
        fields = super().get_fields()
        school = self.get_school()
        for field_name, (model, lookup) in self.scoped_related_fields.items():
            if field_name in fields:
                fields[field_name].queryset = model.objects.filter(**{lookup: school})
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        candidate = copy(self.instance) if self.instance is not None else self.Meta.model()
        for field_name, value in attrs.items():
            setattr(candidate, field_name, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc
        return attrs


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "email", "phone_number", "address", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class SchoolProfileSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source="phone_number", read_only=True)

    class Meta:
        model = School
        fields = ["name", "email", "phone", "address", "logo"]
        read_only_fields = fields


class SchoolClassSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = SchoolClass
        fields = ["id", "name", "is_active"]
        read_only_fields = ["id"]


class StudentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"school_class": (SchoolClass, "school")}

    class Meta:
        model = Student
        fields = ["id", "admission_number", "first_name", "last_name", "date_of_birth", "school_class", "is_active", "enrolled_on", "created_at"]
        read_only_fields = ["id", "created_at"]


class AcademicYearSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "is_current"]
        read_only_fields = ["id"]


class TermSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"academic_year": (AcademicYear, "school")}

    class Meta:
        model = Term
        fields = ["id", "academic_year", "name", "sequence", "start_date", "end_date"]
        read_only_fields = ["id"]


class SubjectSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "code", "is_active"]
        read_only_fields = ["id"]


class ClassSubjectSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "school_class": (SchoolClass, "school"),
        "subject": (Subject, "school"),
        "academic_year": (AcademicYear, "school"),
    }

    class Meta:
        model = ClassSubject
        fields = ["id", "school_class", "subject", "academic_year"]
        read_only_fields = ["id"]


class StudentEnrollmentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student": (Student, "school_class__school"),
        "school_class": (SchoolClass, "school"),
        "academic_year": (AcademicYear, "school"),
    }

    class Meta:
        model = StudentEnrollment
        fields = ["id", "student", "school_class", "academic_year", "enrolled_on", "left_on"]
        read_only_fields = ["id"]


class FeeSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "academic_year": (AcademicYear, "school"),
        "term": (Term, "academic_year__school"),
        "school_class": (SchoolClass, "school"),
    }

    class Meta:
        model = Fee
        fields = ["id", "academic_year", "term", "school_class", "name", "amount", "due_date", "is_active"]
        read_only_fields = ["id"]


class StudentFeeAssignmentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student": (Student, "school_class__school"),
        "fee": (Fee, "school"),
    }

    class Meta:
        model = StudentFeeAssignment
        fields = ["id", "student", "fee", "amount_owed", "assigned_on"]
        read_only_fields = ["id"]


class PaymentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"student_fee_assignment": (StudentFeeAssignment, "student__school_class__school")}

    class Meta:
        model = Payment
        fields = ["id", "student_fee_assignment", "amount", "paid_at", "method", "reference", "notes", "recorded_by", "created_at"]
        read_only_fields = ["id", "recorded_by", "created_at"]


class FinancialLedgerEntrySerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student": (Student, "school_class__school"),
        "fee_assignment": (StudentFeeAssignment, "student__school_class__school"),
        "payment": (Payment, "student_fee_assignment__student__school_class__school"),
    }

    class Meta:
        model = FinancialLedgerEntry
        fields = ["id", "student", "entry_type", "amount", "occurred_at", "description", "fee_assignment", "payment", "created_at"]
        read_only_fields = ["id", "created_at"]


class ReceiptSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"payment": (Payment, "student_fee_assignment__student__school_class__school")}

    class Meta:
        model = Receipt
        fields = ["id", "receipt_number", "payment", "issued_at"]
        read_only_fields = ["id"]


class AcademicResultSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student_enrollment": (StudentEnrollment, "school_class__school"),
        "term": (Term, "academic_year__school"),
        "class_subject": (ClassSubject, "school_class__school"),
    }

    class Meta:
        model = AcademicResult
        fields = ["id", "student_enrollment", "term", "class_subject", "score", "maximum_score", "comment", "recorded_by", "recorded_at"]
        read_only_fields = ["id", "recorded_by", "recorded_at"]


class ReportCardSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student_enrollment": (StudentEnrollment, "school_class__school"),
        "term": (Term, "academic_year__school"),
    }

    class Meta:
        model = ReportCard
        fields = ["id", "student_enrollment", "term", "generated_at", "file"]
        read_only_fields = ["id", "generated_at"]


class NotificationSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "message", "is_read", "created_at"]
        read_only_fields = ["id", "created_at"]


class SchoolParentStudentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"student": (Student, "school_class__school")}

    class Meta:
        model = ParentStudent
        fields = ["id", "parent", "student", "relationship", "is_primary_contact"]
        read_only_fields = ["id"]


class ParentStudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ["id", "admission_number", "first_name", "last_name", "date_of_birth", "school_class", "is_active"]
        read_only_fields = fields


class ParentPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "student_fee_assignment", "amount", "paid_at", "method", "reference", "notes", "created_at"]
        read_only_fields = fields


class ParentReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = ["id", "receipt_number", "payment", "issued_at"]
        read_only_fields = fields


class ParentResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicResult
        fields = ["id", "student_enrollment", "term", "class_subject", "score", "maximum_score", "comment", "recorded_at"]
        read_only_fields = fields


class ParentReportCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportCard
        fields = ["id", "student_enrollment", "term", "generated_at", "file"]
        read_only_fields = fields


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "role"]
