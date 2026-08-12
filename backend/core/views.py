from django.http import FileResponse, Http404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
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
)
from .permissions import IsParent, IsPlatformAdministrator, IsSchoolAdministrator
from .serializers import (
    AcademicResultSerializer,
    AcademicYearSerializer,
    ClassSubjectSerializer,
    CurrentUserSerializer,
    FeeSerializer,
    FinancialLedgerEntrySerializer,
    NotificationSerializer,
    ParentPaymentSerializer,
    ParentReceiptSerializer,
    ParentReportCardSerializer,
    ParentResultSerializer,
    ParentStudentSerializer,
    PaymentSerializer,
    ReceiptSerializer,
    ReportCardSerializer,
    SchoolClassSerializer,
    SchoolParentStudentSerializer,
    SchoolSerializer,
    StudentEnrollmentSerializer,
    StudentFeeAssignmentSerializer,
    StudentSerializer,
    SubjectSerializer,
    TermSerializer,
)
from .tenant import ParentScopedQuerysetMixin, SchoolScopedQuerysetMixin


class SchoolAdminViewSet(SchoolScopedQuerysetMixin, viewsets.ModelViewSet):
    permission_classes = [IsSchoolAdministrator]


class SchoolClassViewSet(SchoolAdminViewSet):
    queryset = SchoolClass.objects.all()
    serializer_class = SchoolClassSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())


class StudentViewSet(SchoolAdminViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    school_lookup = "school_class__school"


class AcademicYearViewSet(SchoolAdminViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())


class TermViewSet(SchoolAdminViewSet):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    school_lookup = "academic_year__school"


class SubjectViewSet(SchoolAdminViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())


class ClassSubjectViewSet(SchoolAdminViewSet):
    queryset = ClassSubject.objects.all()
    serializer_class = ClassSubjectSerializer
    school_lookup = "school_class__school"


class StudentEnrollmentViewSet(SchoolAdminViewSet):
    queryset = StudentEnrollment.objects.all()
    serializer_class = StudentEnrollmentSerializer
    school_lookup = "school_class__school"


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


class NotificationViewSet(SchoolAdminViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school())


class SchoolParentStudentViewSet(SchoolAdminViewSet):
    queryset = ParentStudent.objects.all()
    serializer_class = SchoolParentStudentSerializer
    school_lookup = "student__school_class__school"


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
