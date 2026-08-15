from copy import copy
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from PIL import Image, UnidentifiedImageError

from .models import (
    AcademicResult,
    AcademicYear,
    AuditLog,
    Announcement,
    ClassSubject,
    CommunicationMessage,
    Expense,
    Fee,
    FinancialLedgerEntry,
    Homework,
    HomeworkAttachment,
    Notification,
    Parent,
    ParentCommunicationPreference,
    ParentStudent,
    Payment,
    Receipt,
    RecurringFeeTemplate,
    ReportCard,
    School,
    SchoolCommunicationSettings,
    SchoolClass,
    Student,
    StudentEnrollment,
    StudentFeeAssignment,
    Subject,
    Term,
    TimetableEntry,
    User,
)

HOMEWORK_MAX_ATTACHMENTS = 5
HOMEWORK_MAX_FILE_SIZE = 10 * 1024 * 1024
HOMEWORK_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}


def validate_homework_file(upload):
    extension = Path(upload.name).suffix.lower()
    if extension not in HOMEWORK_EXTENSIONS:
        raise serializers.ValidationError("Supported formats are PDF, DOCX, JPG, JPEG, and PNG.")
    if upload.size > HOMEWORK_MAX_FILE_SIZE:
        raise serializers.ValidationError("Each attachment must be 10 MB or smaller.")
    data = upload.read()
    upload.seek(0)
    valid = False
    content_type = ""
    if extension == ".pdf":
        valid, content_type = data.startswith(b"%PDF-"), "application/pdf"
    elif extension == ".docx":
        try:
            with ZipFile(BytesIO(data)) as archive:
                valid = "[Content_Types].xml" in archive.namelist() and "word/document.xml" in archive.namelist()
        except BadZipFile:
            valid = False
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        try:
            with Image.open(BytesIO(data)) as image:
                image.verify()
                actual = image.format
            valid = actual in {"JPEG", "PNG"} and ((extension in {".jpg", ".jpeg"} and actual == "JPEG") or (extension == ".png" and actual == "PNG"))
            content_type = "image/jpeg" if actual == "JPEG" else "image/png"
        except (UnidentifiedImageError, OSError):
            valid = False
    if not valid:
        raise serializers.ValidationError("The attachment contents do not match a supported file format.")
    return content_type


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


class HomeworkAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    def get_download_url(self, attachment):
        request = self.context.get("request")
        route = "parent/homework" if self.context.get("parent") else "school/homework"
        path = f"/api/{route}/{attachment.homework_id}/attachments/{attachment.id}/download/"
        if self.context.get("parent") and request:
            student = request.query_params.get("student")
            if student:
                path += f"?student={student}"
        return request.build_absolute_uri(path) if request else path

    class Meta:
        model = HomeworkAttachment
        fields = ["id", "original_name", "content_type", "size", "created_at", "download_url"]
        read_only_fields = fields


class HomeworkSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"school_class": (SchoolClass, "school"), "subject": (Subject, "school")}
    attachments = serializers.SerializerMethodField()
    uploaded_attachments = serializers.ListField(child=serializers.FileField(), required=False, write_only=True)
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True, allow_null=True)
    created_by_name = serializers.SerializerMethodField()

    def get_created_by_name(self, homework):
        return homework.created_by.get_full_name() or homework.created_by.username

    def get_attachments(self, homework):
        active = homework.attachments.filter(expires_at__gt=timezone.now())
        return HomeworkAttachmentSerializer(active, many=True, context=self.context).data

    def validate_uploaded_attachments(self, files):
        existing = self.instance.attachments.filter(expires_at__gt=timezone.now()).count() if self.instance else 0
        if existing + len(files) > HOMEWORK_MAX_ATTACHMENTS:
            raise serializers.ValidationError(f"A homework item may have at most {HOMEWORK_MAX_ATTACHMENTS} attachments.")
        for upload in files:
            upload.validated_content_type = validate_homework_file(upload)
        return files

    def validate(self, attrs):
        if "school" in self.initial_data or "school_id" in self.initial_data or "created_by" in self.initial_data:
            raise serializers.ValidationError({"school": "School ownership and creator are controlled by the authenticated account."})
        files = attrs.pop("uploaded_attachments", [])
        candidate = copy(self.instance) if self.instance is not None else Homework()
        for field_name, value in attrs.items():
            setattr(candidate, field_name, value)
        candidate.school = self.get_school()
        candidate.created_by = self.instance.created_by if self.instance else self.context["request"].user
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc
        attrs["uploaded_attachments"] = files
        return attrs

    def _save_attachments(self, homework, files):
        for upload in files:
            HomeworkAttachment.objects.create(homework=homework, file=upload, original_name=Path(upload.name).name[:255], content_type=upload.validated_content_type, size=upload.size)

    def create(self, validated_data):
        files = validated_data.pop("uploaded_attachments", [])
        homework = Homework.objects.create(**validated_data)
        self._save_attachments(homework, files)
        return homework

    def update(self, instance, validated_data):
        files = validated_data.pop("uploaded_attachments", [])
        instance = super().update(instance, validated_data)
        self._save_attachments(instance, files)
        return instance

    class Meta:
        model = Homework
        fields = ["id", "title", "instructions", "school_class", "class_name", "subject", "subject_name", "date_assigned", "due_date", "status", "created_by_name", "created_at", "updated_at", "attachments", "uploaded_attachments"]
        read_only_fields = ["id", "class_name", "subject_name", "created_by_name", "created_at", "updated_at", "attachments"]


class ParentHomeworkSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True, allow_null=True)

    def get_attachments(self, homework):
        active = homework.attachments.filter(expires_at__gt=timezone.now())
        return HomeworkAttachmentSerializer(active, many=True, context=self.context).data

    class Meta:
        model = Homework
        fields = ["id", "title", "instructions", "class_name", "subject_name", "date_assigned", "due_date", "attachments"]
        read_only_fields = fields


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "email", "phone_number", "address", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class SchoolProfileSerializer(serializers.ModelSerializer):
    MAX_LOGO_SIZE = 2 * 1024 * 1024

    phone = serializers.CharField(source="phone_number")

    def validate_default_currency(self, value):
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise serializers.ValidationError("Use a three-letter uppercase currency code.")
        return normalized

    def validate(self, attrs):
        currency = attrs.get("default_currency")
        if currency and self.instance and currency != self.instance.default_currency:
            has_finance = Fee.objects.filter(school=self.instance).exists() or StudentFeeAssignment.objects.filter(student__school=self.instance).exists() or Payment.objects.filter(student_fee_assignment__student__school=self.instance).exists() or FinancialLedgerEntry.objects.filter(student__school=self.instance).exists()
            if has_finance:
                raise serializers.ValidationError({"default_currency": "Currency cannot be changed after financial records exist; this protects historical amounts."})
        return attrs

    def validate_logo(self, logo):
        if logo.size > self.MAX_LOGO_SIZE:
            raise serializers.ValidationError("The logo must be 2 MB or smaller.")
        if getattr(logo, "content_type", "") and not logo.content_type.startswith("image/"):
            raise serializers.ValidationError("Upload an image file for the school logo.")
        return logo

    class Meta:
        model = School
        fields = ["name", "email", "phone", "address", "default_currency", "logo"]


class SchoolClassSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = SchoolClass
        fields = ["id", "name", "is_active"]
        read_only_fields = ["id"]


class StudentWriteSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"school_class": (SchoolClass, "school")}

    class Meta:
        model = Student
        fields = ["id", "admission_number", "first_name", "last_name", "date_of_birth", "school_class", "is_active", "enrolled_on", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        if "school" in self.initial_data or "school_id" in self.initial_data:
            raise serializers.ValidationError({"school": "School ownership is controlled by the authenticated account."})
        candidate = copy(self.instance) if self.instance is not None else Student()
        school = self.get_school()
        for field_name, value in attrs.items():
            setattr(candidate, field_name, value)
        candidate.school = school
        if self.instance is not None:
            next_class = attrs.get("school_class", self.instance.school_class)
            if next_class.pk != self.instance.school_class_id:
                raise serializers.ValidationError({
                    "school_class": "Use the student transfer action to change classes.",
                })
        admission_number = attrs.get("admission_number", getattr(self.instance, "admission_number", None))
        duplicate = Student.objects.filter(school=school, admission_number=admission_number)
        if self.instance is not None:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError({
                "admission_number": "A student with this admission number already exists in this school.",
            })
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc
        return attrs


class StudentTransferSerializer(SchoolScopedSerializerMixin, serializers.Serializer):
    scoped_related_fields = {"school_class": (SchoolClass, "school")}

    school_class = serializers.PrimaryKeyRelatedField(queryset=SchoolClass.objects.none())
    transfer_effective_date = serializers.DateField()

    def validate(self, attrs):
        return attrs


class StudentListSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    class_name = serializers.CharField(source="school_class.name", read_only=True)

    def get_display_name(self, student):
        return f"{student.first_name} {student.last_name}".strip()

    class Meta:
        model = Student
        fields = ["id", "admission_number", "first_name", "last_name", "display_name", "class_name", "is_active"]
        read_only_fields = fields


class StudentParentLinkSerializer(serializers.ModelSerializer):
    parent_name = serializers.SerializerMethodField()
    phone = serializers.CharField(source="parent.phone_number", read_only=True)
    username = serializers.CharField(source="parent.user.username", read_only=True)

    def get_parent_name(self, link):
        return link.parent.user.get_full_name() or link.parent.user.username

    class Meta:
        model = ParentStudent
        fields = ["id", "parent", "parent_name", "username", "phone", "relationship", "is_primary_contact"]
        read_only_fields = fields


class StudentEnrollmentHistorySerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    academic_year = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = StudentEnrollment
        fields = ["id", "academic_year", "class_name", "enrolled_on", "left_on"]
        read_only_fields = fields


class StudentDetailSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    parents = StudentParentLinkSerializer(source="parent_links", many=True, read_only=True)
    enrollment_history = StudentEnrollmentHistorySerializer(source="enrollments", many=True, read_only=True)

    def get_display_name(self, student):
        return f"{student.first_name} {student.last_name}".strip()

    class Meta:
        model = Student
        fields = [
            "id", "admission_number", "first_name", "last_name", "display_name",
            "date_of_birth", "school_class", "class_name", "is_active", "enrolled_on",
            "created_at", "parents", "enrollment_history",
        ]
        read_only_fields = fields


class AvailableParentSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)
    phone = serializers.CharField(source="phone_number", read_only=True)

    def get_display_name(self, parent):
        return parent.user.get_full_name() or parent.user.username

    class Meta:
        model = Parent
        fields = ["id", "display_name", "username", "phone"]
        read_only_fields = fields


class ParentListSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="phone_number", read_only=True)
    child_count = serializers.SerializerMethodField()

    def get_display_name(self, parent):
        return parent.user.get_full_name() or parent.user.username

    def get_child_count(self, parent):
        return len(parent.student_links.all())

    class Meta:
        model = Parent
        fields = ["id", "display_name", "username", "email", "phone", "child_count"]
        read_only_fields = fields


class ParentChildSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    class_name = serializers.CharField(source="student.school_class.name", read_only=True)

    def get_display_name(self, link):
        return f"{link.student.first_name} {link.student.last_name}".strip()

    class Meta:
        model = ParentStudent
        fields = ["id", "student", "display_name", "admission_number", "class_name", "relationship", "is_primary_contact"]
        read_only_fields = fields


class ParentDetailSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    children = ParentChildSerializer(source="student_links", many=True, read_only=True)

    class Meta:
        model = Parent
        fields = ["id", "username", "email", "first_name", "last_name", "phone_number", "address", "children"]
        read_only_fields = fields


class ParentWriteSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False)
    address = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    children = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

    def validate(self, attrs):
        if "school" in self.initial_data or "school_id" in self.initial_data:
            raise serializers.ValidationError({"school": "School ownership is controlled by the authenticated account."})
        if self.instance is None:
            for field in ("username", "password", "phone_number"):
                if not attrs.get(field):
                    raise serializers.ValidationError({field: "This field is required."})
            if User.objects.filter(username=attrs["username"]).exists():
                raise serializers.ValidationError({"username": "This username is already in use."})
        if "password" in attrs:
            candidate = self.instance.user if self.instance else User(username=attrs.get("username", ""))
            try:
                validate_password(attrs["password"], candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        school = self.context["school"]
        child_ids = attrs.get("children", [])
        if child_ids:
            children = Student.objects.filter(school=school, id__in=child_ids)
            if children.count() != len(set(child_ids)):
                raise serializers.ValidationError({"children": "Every child must belong to your school."})
        return attrs

    def create(self, validated_data):
        children = validated_data.pop("children", [])
        password = validated_data.pop("password")
        school = self.context["school"]
        user_fields = {key: validated_data.pop(key, "") for key in ("username", "first_name", "last_name", "email")}
        user = User(**user_fields, role=User.Role.PARENT)
        user.set_password(password)
        user.full_clean()
        user.save()
        parent = Parent.objects.create(school=school, user=user, **validated_data)
        for child in Student.objects.filter(school=school, id__in=children):
            ParentStudent.objects.create(parent=parent, student=child)
        return parent

    def update(self, instance, validated_data):
        validated_data.pop("children", None)
        password = validated_data.pop("password", None)
        user_changes = {key: validated_data.pop(key) for key in ("username", "first_name", "last_name", "email") if key in validated_data}
        for key, value in user_changes.items():
            setattr(instance.user, key, value)
        if password:
            instance.user.set_password(password)
        if user_changes or password:
            instance.user.full_clean()
            instance.user.save()
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.full_clean()
        instance.save()
        return instance


class TimetableEntrySerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "school_class": (SchoolClass, "school"),
        "academic_year": (AcademicYear, "school"),
        "term": (Term, "academic_year__school"),
        "subject": (Subject, "school"),
    }
    display_label = serializers.SerializerMethodField()
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    def get_display_label(self, entry):
        return entry.label or (entry.subject.name if entry.subject_id else "")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        candidate = copy(self.instance) if self.instance else TimetableEntry()
        for key, value in attrs.items():
            setattr(candidate, key, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages})) from exc
        overlaps = TimetableEntry.objects.filter(
            school_class=candidate.school_class,
            academic_year=candidate.academic_year,
            term=candidate.term,
            day_of_week=candidate.day_of_week,
            start_time__lt=candidate.end_time,
            end_time__gt=candidate.start_time,
        )
        if self.instance:
            overlaps = overlaps.exclude(pk=self.instance.pk)
        if overlaps.exists():
            raise serializers.ValidationError({"start_time": "This period overlaps an existing timetable entry."})
        return attrs

    class Meta:
        model = TimetableEntry
        fields = ["id", "school_class", "class_name", "academic_year", "academic_year_name", "term", "term_name", "day_of_week", "start_time", "end_time", "subject", "subject_name", "label", "display_label"]
        read_only_fields = ["id", "display_label"]


class AcademicYearSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})
        if attrs.get("is_current", getattr(self.instance, "is_current", False)):
            current = AcademicYear.objects.filter(school=self.get_school(), is_current=True)
            if self.instance:
                current = current.exclude(pk=self.instance.pk)
            if current.exists():
                raise serializers.ValidationError({"is_current": "Only one academic year can be current for this school."})
        return attrs

    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "is_current"]
        read_only_fields = ["id"]


class TermSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"academic_year": (AcademicYear, "school")}
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})
        return attrs

    class Meta:
        model = Term
        fields = ["id", "academic_year", "academic_year_name", "name", "sequence", "start_date", "end_date"]
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
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = ClassSubject
        fields = ["id", "school_class", "class_name", "subject", "subject_name", "academic_year", "academic_year_name"]
        read_only_fields = ["id"]


class StudentEnrollmentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student": (Student, "school"),
        "school_class": (SchoolClass, "school"),
        "academic_year": (AcademicYear, "school"),
    }
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    class_name = serializers.CharField(source="school_class.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    def get_student_name(self, enrollment):
        return f"{enrollment.student.first_name} {enrollment.student.last_name}".strip()

    class Meta:
        model = StudentEnrollment
        fields = ["id", "student", "student_name", "admission_number", "school_class", "class_name", "academic_year", "academic_year_name", "enrolled_on", "left_on"]
        read_only_fields = ["id"]


class FeeSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "academic_year": (AcademicYear, "school"),
        "term": (Term, "academic_year__school"),
        "school_class": (SchoolClass, "school"),
    }
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    class_name = serializers.CharField(source="school_class.name", read_only=True)

    def validate(self, attrs):
        if "school" in self.initial_data or "school_id" in self.initial_data:
            raise serializers.ValidationError({"school": "School ownership is controlled by the authenticated account."})
        attrs = serializers.ModelSerializer.validate(self, attrs)
        currency = attrs.get("currency", getattr(self.instance, "currency", self.get_school().default_currency))
        if currency != self.get_school().default_currency:
            raise serializers.ValidationError({"currency": "This school supports its default currency only."})
        candidate = copy(self.instance) if self.instance is not None else Fee(school=self.get_school())
        for field_name, value in attrs.items():
            setattr(candidate, field_name, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages})) from exc
        return attrs

    class Meta:
        model = Fee
        fields = ["id", "academic_year", "academic_year_name", "term", "term_name", "school_class", "class_name", "name", "amount", "currency", "due_date", "is_active"]
        read_only_fields = ["id"]


class StudentFeeAssignmentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student": (Student, "school_class__school"),
        "fee": (Fee, "school"),
    }
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    fee_name = serializers.CharField(source="fee.name", read_only=True)
    class_name = serializers.CharField(source="student.school_class.name", read_only=True)

    def get_student_name(self, assignment):
        return f"{assignment.student.first_name} {assignment.student.last_name}".strip()

    def validate(self, attrs):
        if "school" in self.initial_data or "school_id" in self.initial_data:
            raise serializers.ValidationError({"school": "School ownership is controlled by the authenticated account."})
        return super().validate(attrs)

    class Meta:
        model = StudentFeeAssignment
        fields = ["id", "student", "student_name", "admission_number", "class_name", "fee", "fee_name", "amount_owed", "currency", "assigned_on"]
        read_only_fields = ["id"]


class PaymentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"student_fee_assignment": (StudentFeeAssignment, "student__school_class__school")}
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student_fee_assignment.student.admission_number", read_only=True)
    fee_name = serializers.CharField(source="student_fee_assignment.fee.name", read_only=True)
    outstanding_before = serializers.SerializerMethodField()

    def get_student_name(self, payment):
        student = payment.student_fee_assignment.student
        return f"{student.first_name} {student.last_name}".strip()

    def get_outstanding_before(self, payment):
        from .finance import assignment_totals
        _, paid, _ = assignment_totals(payment.student_fee_assignment)
        return payment.student_fee_assignment.amount_owed - paid + payment.amount

    def validate(self, attrs):
        if "recorded_by" in self.initial_data:
            raise serializers.ValidationError({"recorded_by": "The recording administrator is set by the server."})
        if "school" in self.initial_data or "school_id" in self.initial_data:
            raise serializers.ValidationError({"school": "School ownership is controlled by the authenticated account."})
        return super().validate(attrs)

    class Meta:
        model = Payment
        fields = ["id", "student_fee_assignment", "student_name", "admission_number", "fee_name", "amount", "currency", "paid_at", "method", "reference", "notes", "recorded_by", "created_at", "is_reversed", "reversed_at", "reversal_reason", "outstanding_before"]
        read_only_fields = ["id", "currency", "recorded_by", "created_at", "is_reversed", "reversed_at", "reversal_reason", "outstanding_before"]


class FinancialLedgerEntrySerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student": (Student, "school_class__school"),
        "fee_assignment": (StudentFeeAssignment, "student__school_class__school"),
        "payment": (Payment, "student_fee_assignment__student__school_class__school"),
    }
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    debit = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()

    def get_student_name(self, entry):
        return f"{entry.student.first_name} {entry.student.last_name}".strip()

    def get_debit(self, entry):
        return entry.amount if entry.entry_type == FinancialLedgerEntry.EntryType.CHARGE else None

    def get_credit(self, entry):
        return entry.amount if entry.entry_type == FinancialLedgerEntry.EntryType.PAYMENT else None

    class Meta:
        model = FinancialLedgerEntry
        fields = ["id", "student", "student_name", "admission_number", "entry_type", "amount", "currency", "debit", "credit", "occurred_at", "description", "fee_assignment", "payment", "created_at"]
        read_only_fields = fields


class ReceiptSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"payment": (Payment, "student_fee_assignment__student__school_class__school")}
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="payment.student_fee_assignment.student.admission_number", read_only=True)
    payment_amount = serializers.DecimalField(source="payment.amount", max_digits=12, decimal_places=2, read_only=True)
    paid_at = serializers.DateTimeField(source="payment.paid_at", read_only=True)
    payment_method = serializers.CharField(source="payment.method", read_only=True)
    reference = serializers.CharField(source="payment.reference", read_only=True)
    fee_name = serializers.CharField(source="payment.student_fee_assignment.fee.name", read_only=True)

    def get_student_name(self, receipt):
        student = receipt.payment.student_fee_assignment.student
        return f"{student.first_name} {student.last_name}".strip()

    class Meta:
        model = Receipt
        fields = ["id", "receipt_number", "payment", "student_name", "admission_number", "payment_amount", "paid_at", "payment_method", "reference", "fee_name", "issued_at", "is_reversed"]
        read_only_fields = fields


class RecurringFeeTemplateSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {"academic_year": (AcademicYear, "school"), "term": (Term, "academic_year__school"), "school_class": (SchoolClass, "school")}
    class_name = serializers.CharField(source="school_class.name", read_only=True)

    class Meta:
        model = RecurringFeeTemplate
        fields = ["id", "academic_year", "term", "school_class", "class_name", "name", "amount", "currency", "start_month", "end_month", "is_active"]
        read_only_fields = ["id"]


class ExpenseSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()

    def get_recorded_by_name(self, expense):
        return expense.recorded_by.get_full_name() or expense.recorded_by.username

    class Meta:
        model = Expense
        fields = [
            "id", "expense_date", "category", "description", "amount", "currency",
            "payment_method", "reference", "notes", "recorded_by", "recorded_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "currency", "recorded_by", "recorded_by_name", "created_at", "updated_at"]


class AcademicResultSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student_enrollment": (StudentEnrollment, "school_class__school"),
        "term": (Term, "academic_year__school"),
        "class_subject": (ClassSubject, "school_class__school"),
    }
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student_enrollment.student.admission_number", read_only=True)
    class_name = serializers.CharField(source="student_enrollment.school_class.name", read_only=True)
    academic_year_name = serializers.CharField(source="student_enrollment.academic_year.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    subject_name = serializers.CharField(source="class_subject.subject.name", read_only=True)
    percentage = serializers.SerializerMethodField()

    def get_student_name(self, result):
        student = result.student_enrollment.student
        return f"{student.first_name} {student.last_name}".strip()

    def get_percentage(self, result):
        return round((result.score / result.maximum_score) * 100, 2)

    class Meta:
        model = AcademicResult
        fields = ["id", "student_enrollment", "student_name", "admission_number", "class_name", "academic_year_name", "term", "term_name", "class_subject", "subject_name", "score", "maximum_score", "percentage", "comment", "recorded_by", "recorded_at"]
        read_only_fields = ["id", "recorded_by", "recorded_at"]


class ReportCardSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student_enrollment": (StudentEnrollment, "school_class__school"),
        "term": (Term, "academic_year__school"),
    }
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student_enrollment.student.admission_number", read_only=True)
    class_name = serializers.CharField(source="student_enrollment.school_class.name", read_only=True)
    academic_year_name = serializers.CharField(source="student_enrollment.academic_year.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)

    def get_student_name(self, report_card):
        student = report_card.student_enrollment.student
        return f"{student.first_name} {student.last_name}".strip()

    class Meta:
        model = ReportCard
        fields = ["id", "student_enrollment", "student_name", "admission_number", "class_name", "academic_year_name", "term", "term_name", "generated_at", "file"]
        read_only_fields = ["id", "generated_at"]


class NotificationSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    def get_student_name(self, notification):
        if not notification.student_id:
            return ""
        return f"{notification.student.first_name} {notification.student.last_name}".strip()

    class Meta:
        model = Notification
        fields = ["id", "title", "message", "student_name", "is_read", "created_at"]
        read_only_fields = ["id", "created_at"]


class SchoolCommunicationSettingsSerializer(serializers.ModelSerializer):
    integration_available = serializers.SerializerMethodField()

    def get_integration_available(self, settings):
        from django.conf import settings as django_settings
        return bool(getattr(django_settings, "MTM_N8N_INTEGRATION_SECRET", ""))

    class Meta:
        model = SchoolCommunicationSettings
        fields = [
            "whatsapp_enabled",
            "payment_receipt_notifications_enabled",
            "fee_reminders_enabled",
            "report_card_notifications_enabled",
            "whatsapp_announcements_enabled",
            "integration_available",
        ]
        read_only_fields = ["integration_available"]


class ParentCommunicationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParentCommunicationPreference
        fields = ["whatsapp_status", "whatsapp_phone", "opted_in_at", "opted_out_at", "consent_source", "updated_at"]
        read_only_fields = ["opted_in_at", "opted_out_at", "updated_at"]

    def validate(self, attrs):
        instance = self.instance or ParentCommunicationPreference(parent=self.context["parent"])
        for field, value in attrs.items():
            setattr(instance, field, value)
        now = timezone.now()
        if instance.whatsapp_status == ParentCommunicationPreference.WhatsAppStatus.OPTED_IN:
            instance.opted_in_at = instance.opted_in_at or now
            instance.opted_out_at = None
        elif instance.whatsapp_status == ParentCommunicationPreference.WhatsAppStatus.OPTED_OUT:
            instance.opted_out_at = instance.opted_out_at or now
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages})) from exc
        attrs["opted_in_at"] = instance.opted_in_at
        attrs["opted_out_at"] = instance.opted_out_at
        return attrs


class AnnouncementSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "school_class": (SchoolClass, "school"),
        "student": (Student, "school"),
        "parent": (Parent, "school"),
    }

    class Meta:
        model = Announcement
        fields = ["id", "title", "message", "audience", "school_class", "student", "parent", "channels", "status", "recipient_count", "created_at", "sent_at"]
        read_only_fields = ["id", "status", "recipient_count", "created_at", "sent_at"]

    def validate_channels(self, value):
        allowed = {CommunicationMessage.Channel.IN_APP, CommunicationMessage.Channel.WHATSAPP}
        if not isinstance(value, list) or not value or not set(value).issubset(allowed):
            raise serializers.ValidationError("Choose one or both of: in_app, whatsapp.")
        return value

    def validate(self, attrs):
        attrs = serializers.ModelSerializer.validate(self, attrs)
        candidate = copy(self.instance) if self.instance else Announcement(school=self.get_school())
        for field, value in attrs.items():
            setattr(candidate, field, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages})) from exc
        return attrs


class CommunicationMessageSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.user.get_full_name", read_only=True)
    student_name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    def get_student_name(self, message):
        if not message.student_id:
            return ""
        return f"{message.student.first_name} {message.student.last_name}".strip()

    def get_description(self, message):
        return message.payload.get("title") or message.payload.get("receipt_number") or message.event_type.replace("_", " ")

    class Meta:
        model = CommunicationMessage
        fields = ["id", "parent", "parent_name", "student", "student_name", "channel", "event_type", "template_key", "status", "description", "created_at", "sent_at", "delivered_at", "read_at", "failed_at", "failure_reason"]
        read_only_fields = fields


class ParentNotificationSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    def get_student_name(self, notification):
        return f"{notification.student.first_name} {notification.student.last_name}".strip() if notification.student_id else ""

    class Meta:
        model = Notification
        fields = ["id", "title", "message", "student_name", "is_read", "created_at"]
        read_only_fields = ["id", "title", "message", "student_name", "created_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    def get_actor_name(self, log):
        if not log.actor_id:
            return "System"
        return log.actor.get_full_name() or log.actor.username

    class Meta:
        model = AuditLog
        fields = ["id", "actor_name", "action", "resource_type", "resource_id", "description", "created_at"]
        read_only_fields = fields


class SchoolParentStudentSerializer(SchoolScopedSerializerMixin, serializers.ModelSerializer):
    scoped_related_fields = {
        "student": (Student, "school"),
        "parent": (Parent, "school"),
    }

    def get_fields(self):
        fields = super().get_fields()
        fields["parent"].queryset = fields["parent"].queryset.distinct()
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        student = attrs.get("student", getattr(self.instance, "student", None))
        if parent and student and parent.school_id != student.school_id:
            raise serializers.ValidationError({"parent": "Parent and student must belong to the same school."})
        if attrs.get("is_primary_contact", getattr(self.instance, "is_primary_contact", False)):
            student = attrs.get("student", getattr(self.instance, "student", None))
            existing = ParentStudent.objects.filter(student=student, is_primary_contact=True)
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError({"is_primary_contact": "This student already has a primary contact."})
        return attrs

    class Meta:
        model = ParentStudent
        fields = ["id", "parent", "student", "relationship", "is_primary_contact"]
        read_only_fields = ["id"]


class ParentStudentSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    class_name = serializers.CharField(source="school_class.name", read_only=True)

    def get_display_name(self, student):
        return f"{student.first_name} {student.last_name}".strip()

    class Meta:
        model = Student
        fields = ["id", "admission_number", "first_name", "last_name", "display_name", "date_of_birth", "school_class", "class_name", "is_active"]
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
