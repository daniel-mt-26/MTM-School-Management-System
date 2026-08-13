from datetime import timedelta

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AcademicResult,
    AcademicYear,
    ClassSubject,
    Fee,
    FinancialLedgerEntry,
    Notification,
    Parent,
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
    TimetableEntry,
)
from .permissions import IsParent, IsPlatformAdministrator, IsSchoolAdministrator
from .serializers import (
    AcademicResultSerializer,
    AcademicYearSerializer,
    AvailableParentSerializer,
    ClassSubjectSerializer,
    CurrentUserSerializer,
    FeeSerializer,
    FinancialLedgerEntrySerializer,
    NotificationSerializer,
    ParentPaymentSerializer,
    ParentDetailSerializer,
    ParentListSerializer,
    ParentWriteSerializer,
    ParentReceiptSerializer,
    ParentReportCardSerializer,
    ParentResultSerializer,
    ParentStudentSerializer,
    PaymentSerializer,
    ReceiptSerializer,
    ReportCardSerializer,
    SchoolClassSerializer,
    SchoolParentStudentSerializer,
    SchoolProfileSerializer,
    SchoolSerializer,
    StudentEnrollmentSerializer,
    StudentFeeAssignmentSerializer,
    StudentDetailSerializer,
    StudentListSerializer,
    StudentTransferSerializer,
    StudentWriteSerializer,
    SubjectSerializer,
    TermSerializer,
    TimetableEntrySerializer,
)
from .tenant import ParentScopedQuerysetMixin, SchoolScopedQuerysetMixin


class SchoolAdminViewSet(SchoolScopedQuerysetMixin, viewsets.ModelViewSet):
    permission_classes = [IsSchoolAdministrator]


class SchoolProfileView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request):
        school = request.user.school_administrator.school
        return Response(SchoolProfileSerializer(school, context={"request": request}).data)

    def patch(self, request):
        school = request.user.school_administrator.school
        serializer = SchoolProfileSerializer(
            school,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SchoolSearchView(APIView):
    permission_classes = [IsSchoolAdministrator]
    result_limit = 10

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        empty_results = {"students": [], "parents": [], "classes": []}
        if len(query) < 2:
            return Response(empty_results)

        school = request.user.school_administrator.school
        students = (
            Student.objects.filter(school=school)
            .filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(admission_number__icontains=query)
            )
            .select_related("school_class")
            .order_by("last_name", "first_name", "id")[: self.result_limit]
        )
        parents = (
            Parent.objects.filter(school=school)
            .filter(
                Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__username__icontains=query)
                | Q(phone_number__icontains=query)
            )
            .select_related("user")
            .distinct()
            .order_by("user__last_name", "user__first_name", "id")[: self.result_limit]
        )
        classes = (
            SchoolClass.objects.filter(school=school, name__icontains=query)
            .order_by("name", "id")[: self.result_limit]
        )

        return Response({
            "students": [
                {
                    "id": student.id,
                    "display_name": f"{student.first_name} {student.last_name}".strip(),
                    "admission_number": student.admission_number,
                    "class_name": student.school_class.name,
                }
                for student in students
            ],
            "parents": [
                {
                    "id": parent.id,
                    "display_name": parent.user.get_full_name() or parent.user.username,
                    "username": parent.user.username,
                    "phone": parent.phone_number,
                }
                for parent in parents
            ],
            "classes": [{"id": school_class.id, "name": school_class.name} for school_class in classes],
        })


class SchoolClassViewSet(SchoolAdminViewSet):
    queryset = SchoolClass.objects.all()
    serializer_class = SchoolClassSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())

    def get_queryset(self):
        queryset = super().get_queryset()
        if query := self.request.query_params.get("q", "").strip():
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by("name", "id")


class StudentViewSet(SchoolAdminViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentWriteSerializer
    school_lookup = "school"

    def get_queryset(self):
        queryset = (
            super().get_queryset()
            .select_related("school_class")
            .prefetch_related(
                Prefetch(
                    "enrollments",
                    queryset=StudentEnrollment.objects.select_related("academic_year", "school_class").order_by(
                        "academic_year__start_date", "enrolled_on", "id"
                    ),
                ),
                "parent_links__parent__user",
            )
        )
        query = self.request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(admission_number__icontains=query)
            )
        class_id = self.request.query_params.get("school_class")
        if class_id:
            queryset = queryset.filter(school_class_id=class_id)
        active = self.request.query_params.get("is_active", "").lower()
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        return queryset.order_by("last_name", "first_name", "id")

    def get_serializer_class(self):
        if self.action == "list":
            return StudentListSerializer
        if self.action == "retrieve":
            return StudentDetailSerializer
        return StudentWriteSerializer

    def perform_create(self, serializer):
        academic_year = AcademicYear.objects.filter(school=self.get_school(), is_current=True).first()
        if not academic_year:
            raise ValidationError({"enrolled_on": "A current academic year is required to enroll a student."})
        with transaction.atomic():
            student = serializer.save(school=self.get_school())
            StudentEnrollment.objects.create(
                student=student,
                school_class=student.school_class,
                academic_year=academic_year,
                enrolled_on=student.enrolled_on,
            )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def transfer(self, request, *args, **kwargs):
        student = get_object_or_404(self.get_queryset().select_for_update(), pk=kwargs["pk"])
        serializer = StudentTransferSerializer(data=request.data, context={"school": self.get_school()})
        serializer.is_valid(raise_exception=True)
        next_class = serializer.validated_data["school_class"]
        effective_date = serializer.validated_data["transfer_effective_date"]

        if next_class.pk == student.school_class_id:
            return Response(StudentDetailSerializer(student, context={"request": request}).data)

        open_enrollments = list(
            student.enrollments.select_for_update().select_related("academic_year").filter(left_on__isnull=True)
        )
        if len(open_enrollments) != 1:
            raise ValidationError({"transfer_effective_date": "The student must have exactly one open enrollment before transfer."})
        current_enrollment = open_enrollments[0]
        if effective_date <= current_enrollment.enrolled_on:
            raise ValidationError({
                "transfer_effective_date": "The transfer date must be after the current enrollment start date.",
            })
        if not current_enrollment.academic_year.start_date <= effective_date <= current_enrollment.academic_year.end_date:
            raise ValidationError({
                "transfer_effective_date": "The transfer date must fall within the current enrollment's academic year.",
            })

        current_enrollment.left_on = effective_date - timedelta(days=1)
        current_enrollment.save(update_fields=["left_on"])
        StudentEnrollment.objects.create(
            student=student,
            school_class=next_class,
            academic_year=current_enrollment.academic_year,
            enrolled_on=effective_date,
        )
        student.school_class = next_class
        student.full_clean()
        student.save(update_fields=["school_class"])
        refreshed = self.get_queryset().get(pk=student.pk)
        return Response(StudentDetailSerializer(refreshed, context={"request": request}).data)


class AvailableParentView(APIView):
    permission_classes = [IsSchoolAdministrator]
    result_limit = 20

    def get(self, request):
        school = request.user.school_administrator.school
        query = request.query_params.get("q", "").strip()
        parents = Parent.objects.filter(school=school)
        if query:
            parents = parents.filter(
                Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__username__icontains=query)
                | Q(phone_number__icontains=query)
            )
        parents = parents.select_related("user").distinct().order_by("user__last_name", "user__first_name", "id")[: self.result_limit]
        return Response(AvailableParentSerializer(parents, many=True).data)


class ParentViewSet(SchoolAdminViewSet):
    queryset = Parent.objects.all()
    school_lookup = "school"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("user").prefetch_related("student_links__student__school_class")
        query = self.request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__username__icontains=query)
                | Q(user__email__icontains=query)
                | Q(phone_number__icontains=query)
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return ParentListSerializer
        if self.action == "retrieve":
            return ParentDetailSerializer
        return ParentWriteSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        parent = Parent.objects.select_related("user").prefetch_related("student_links__student__school_class").get(pk=serializer.instance.pk)
        return Response(ParentDetailSerializer(parent).data, status=201)

    def update(self, request, *args, **kwargs):
        parent = self.get_object()
        serializer = self.get_serializer(parent, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        parent.refresh_from_db()
        return Response(ParentDetailSerializer(parent).data)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")


class TimetableEntryViewSet(SchoolAdminViewSet):
    queryset = TimetableEntry.objects.all()
    serializer_class = TimetableEntrySerializer
    school_lookup = "school_class__school"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("school_class", "academic_year", "term", "subject")
        for name in ("school_class", "academic_year", "term"):
            if value := self.request.query_params.get(name):
                queryset = queryset.filter(**{f"{name}_id": value})
        return queryset.order_by("day_of_week", "start_time", "end_time", "id")


class ParentStudentTimetableView(APIView):
    permission_classes = [IsParent]

    def get(self, request, student_id):
        student = get_object_or_404(
            Student.objects.select_related("school_class"),
            pk=student_id,
            parent_links__parent=request.user.parent_profile,
        )
        entries = TimetableEntry.objects.filter(school_class=student.school_class)
        if year := request.query_params.get("academic_year"):
            entries = entries.filter(academic_year_id=year)
        if term := request.query_params.get("term"):
            entries = entries.filter(term_id=term)
        return Response(TimetableEntrySerializer(entries, many=True, context={"school": student.school}).data)


class AcademicYearViewSet(SchoolAdminViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())

    def get_queryset(self):
        return super().get_queryset().order_by("-is_current", "-start_date", "id")


class TermViewSet(SchoolAdminViewSet):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    school_lookup = "academic_year__school"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("academic_year")
        if year := self.request.query_params.get("academic_year"):
            queryset = queryset.filter(academic_year_id=year)
        return queryset.order_by("academic_year__start_date", "sequence", "id")


class SubjectViewSet(SchoolAdminViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())

    def get_queryset(self):
        queryset = super().get_queryset()
        if query := self.request.query_params.get("q", "").strip():
            queryset = queryset.filter(Q(name__icontains=query) | Q(code__icontains=query))
        return queryset.order_by("name", "id")


class ClassSubjectViewSet(SchoolAdminViewSet):
    queryset = ClassSubject.objects.all()
    serializer_class = ClassSubjectSerializer
    school_lookup = "school_class__school"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("school_class", "subject", "academic_year")
        for name in ("school_class", "subject", "academic_year"):
            if value := self.request.query_params.get(name):
                queryset = queryset.filter(**{f"{name}_id": value})
        return queryset.order_by("academic_year__start_date", "school_class__name", "subject__name", "id")


class StudentEnrollmentViewSet(SchoolAdminViewSet):
    queryset = StudentEnrollment.objects.all()
    serializer_class = StudentEnrollmentSerializer
    school_lookup = "school_class__school"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("student", "school_class", "academic_year")
        for name in ("student", "school_class", "academic_year"):
            if value := self.request.query_params.get(name):
                queryset = queryset.filter(**{f"{name}_id": value})
        open_only = self.request.query_params.get("open", "").lower()
        if open_only in {"true", "false"}:
            queryset = queryset.filter(left_on__isnull=open_only == "true")
        return queryset.order_by("-academic_year__start_date", "student__last_name", "student__first_name", "-enrolled_on", "id")


class FeeViewSet(SchoolAdminViewSet):
    queryset = Fee.objects.all()
    serializer_class = FeeSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())


class StudentFeeAssignmentViewSet(SchoolAdminViewSet):
    queryset = StudentFeeAssignment.objects.all()
    serializer_class = StudentFeeAssignmentSerializer
    school_lookup = "student__school_class__school"


class PaymentViewSet(SchoolAdminViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    school_lookup = "student_fee_assignment__student__school_class__school"

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


class FinancialLedgerEntryViewSet(SchoolAdminViewSet):
    queryset = FinancialLedgerEntry.objects.all()
    serializer_class = FinancialLedgerEntrySerializer
    school_lookup = "student__school_class__school"


class ReceiptViewSet(SchoolAdminViewSet):
    queryset = Receipt.objects.all()
    serializer_class = ReceiptSerializer
    school_lookup = "payment__student_fee_assignment__student__school_class__school"


class AcademicResultViewSet(SchoolAdminViewSet):
    queryset = AcademicResult.objects.all()
    serializer_class = AcademicResultSerializer
    school_lookup = "student_enrollment__school_class__school"

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            "student_enrollment__student",
            "student_enrollment__school_class",
            "student_enrollment__academic_year",
            "term",
            "class_subject__subject",
        )
        filters = {
            "academic_year": "student_enrollment__academic_year_id",
            "term": "term_id",
            "school_class": "student_enrollment__school_class_id",
            "subject": "class_subject__subject_id",
            "student": "student_enrollment__student_id",
        }
        for param, lookup in filters.items():
            if value := self.request.query_params.get(param):
                queryset = queryset.filter(**{lookup: value})
        return queryset.order_by("student_enrollment__student__last_name", "student_enrollment__student__first_name", "class_subject__subject__name", "id")


class ReportCardDownloadMixin:
    @action(detail=True, methods=["get"])
    def download(self, request, *args, **kwargs):
        report_card = self.get_object()
        if not report_card.file:
            raise Http404("No report-card file is available.")
        return FileResponse(report_card.file.open("rb"), as_attachment=True, filename=report_card.file.name.rsplit("/", 1)[-1])


class ReportCardViewSet(ReportCardDownloadMixin, SchoolAdminViewSet):
    queryset = ReportCard.objects.all()
    serializer_class = ReportCardSerializer
    school_lookup = "student_enrollment__school_class__school"

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            "student_enrollment__student",
            "student_enrollment__school_class",
            "student_enrollment__academic_year",
            "term",
        )
        for param, lookup in {
            "student": "student_enrollment__student_id",
            "academic_year": "student_enrollment__academic_year_id",
            "term": "term_id",
        }.items():
            if value := self.request.query_params.get(param):
                queryset = queryset.filter(**{lookup: value})
        return queryset.order_by("-generated_at", "id")


class NotificationViewSet(SchoolAdminViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())


class SchoolParentStudentViewSet(SchoolAdminViewSet):
    queryset = ParentStudent.objects.all()
    serializer_class = SchoolParentStudentSerializer
    school_lookup = "student__school"


class ParentReadOnlyViewSet(ParentScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsParent]


class ParentStudentViewSet(ParentReadOnlyViewSet):
    queryset = Student.objects.all()
    serializer_class = ParentStudentSerializer
    parent_lookup = "parent_links__parent"


class ParentPaymentViewSet(ParentReadOnlyViewSet):
    queryset = Payment.objects.all()
    serializer_class = ParentPaymentSerializer
    parent_lookup = "student_fee_assignment__student__parent_links__parent"


class ParentReceiptViewSet(ParentReadOnlyViewSet):
    queryset = Receipt.objects.all()
    serializer_class = ParentReceiptSerializer
    parent_lookup = "payment__student_fee_assignment__student__parent_links__parent"


class ParentAcademicResultViewSet(ParentReadOnlyViewSet):
    queryset = AcademicResult.objects.all()
    serializer_class = ParentResultSerializer
    parent_lookup = "student_enrollment__student__parent_links__parent"


class ParentReportCardViewSet(ReportCardDownloadMixin, ParentReadOnlyViewSet):
    queryset = ReportCard.objects.all()
    serializer_class = ParentReportCardSerializer
    parent_lookup = "student_enrollment__student__parent_links__parent"


class PlatformSchoolViewSet(viewsets.ModelViewSet):
    """Platform administrators can manage school accounts, not school-private data."""

    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [IsPlatformAdministrator]


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)
