from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
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
    RecurringFeeTemplate,
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
from .finance import assign_fee, assignment_totals, generate_recurring_charges, record_payment, reverse_payment, student_totals
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
    RecurringFeeTemplateSerializer,
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


def receipt_pdf_response(receipt):
    """A dependency-free, server-generated single-page PDF receipt."""
    payment = receipt.payment
    assignment = payment.student_fee_assignment
    student = assignment.student
    school = student.school
    lines = [school.name, f"Receipt: {receipt.receipt_number}", f"Student: {student.first_name} {student.last_name}", f"Admission: {student.admission_number}", f"Fee: {assignment.fee.name}", f"Amount: {payment.currency} {payment.amount}", f"Paid: {payment.paid_at:%Y-%m-%d %H:%M}", f"Method: {payment.method}", f"Reference: {payment.reference or '-'}", f"Recorded: {payment.created_at:%Y-%m-%d %H:%M}", "STATUS: REVERSED" if receipt.is_reversed else "STATUS: PAID"]
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 12 Tf 50 760 Td " + " ".join(f"({line}) Tj 0 -22 Td" for line in escaped) + " ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>", f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    pdf = "%PDF-1.4\n"; offsets = [0]
    for index, obj in enumerate(objects, 1): offsets.append(len(pdf.encode("latin-1"))); pdf += f"{index} 0 obj\n{obj}\nendobj\n"
    start = len(pdf.encode("latin-1")); pdf += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n" + "".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:]) + f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF"
    response = HttpResponse(pdf.encode("latin-1"), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt-{receipt.receipt_number}.pdf"'
    return response


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
        serializer.save(school=self.get_school(), currency=serializer.validated_data.get("currency", self.get_school().default_currency))

    def get_queryset(self):
        queryset = super().get_queryset().select_related("academic_year", "term", "school_class")
        for name in ("academic_year", "term", "school_class"):
            if value := self.request.query_params.get(name):
                queryset = queryset.filter(**{f"{name}_id": value})
        if query := self.request.query_params.get("q", "").strip():
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by("-academic_year__start_date", "name", "id")

    def destroy(self, request, *args, **kwargs):
        fee = self.get_object()
        if fee.student_assignments.exists():
            raise ValidationError({"detail": "Fees with assignments are preserved as financial history."})
        return super().destroy(request, *args, **kwargs)


class StudentFeeAssignmentViewSet(SchoolAdminViewSet):
    queryset = StudentFeeAssignment.objects.all()
    serializer_class = StudentFeeAssignmentSerializer
    school_lookup = "student__school_class__school"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("student__school_class", "fee")
        for name in ("student", "fee"):
            if value := self.request.query_params.get(name):
                queryset = queryset.filter(**{f"{name}_id": value})
        if school_class := self.request.query_params.get("school_class"):
            queryset = queryset.filter(student__school_class_id=school_class)
        return queryset.order_by("student__last_name", "student__first_name", "fee__name", "id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if StudentFeeAssignment.objects.filter(student=serializer.validated_data["student"], fee=serializer.validated_data["fee"]).exists():
            raise ValidationError({"fee": "This fee is already assigned to this student."})
        assignment, _ = assign_fee(**serializer.validated_data)
        return Response(self.get_serializer(assignment).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="assign-to-class")
    @transaction.atomic
    def assign_to_class(self, request):
        school = self.get_school()
        class_id = request.data.get("school_class")
        fee_id = request.data.get("fee")
        assigned_on = request.data.get("assigned_on")
        if not all((class_id, fee_id, assigned_on)):
            raise ValidationError({"detail": "school_class, fee, and assigned_on are required."})
        school_class = get_object_or_404(SchoolClass, pk=class_id, school=school)
        fee = get_object_or_404(Fee, pk=fee_id, school=school)
        if fee.school_class_id and fee.school_class_id != school_class.id:
            raise ValidationError({"school_class": "This fee is limited to a different class."})
        students = Student.objects.filter(school=school, school_class=school_class, is_active=True)
        created = 0
        already_assigned = 0
        for student in students:
            _, was_created = assign_fee(student=student, fee=fee, amount_owed=fee.amount, assigned_on=assigned_on)
            created += int(was_created)
            already_assigned += int(not was_created)
        return Response({"students_considered": students.count(), "assignments_created": created, "already_assigned": already_assigned})

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")


class PaymentViewSet(SchoolAdminViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    school_lookup = "student_fee_assignment__student__school_class__school"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("student_fee_assignment__student", "student_fee_assignment__fee", "receipt")
        for param, lookup in {"student": "student_fee_assignment__student_id", "fee": "student_fee_assignment__fee_id"}.items():
            if value := self.request.query_params.get(param):
                queryset = queryset.filter(**{lookup: value})
        return queryset.order_by("-paid_at", "-id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment, receipt = record_payment(recorded_by=request.user, **serializer.validated_data)
        data = self.get_serializer(payment).data
        data["receipt_id"] = receipt.id
        data["receipt_number"] = receipt.receipt_number
        return Response(data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    @action(detail=True, methods=["post"])
    def reverse(self, request, *args, **kwargs):
        payment = self.get_object()
        reversed_payment = reverse_payment(payment_id=payment.id, reason=request.data.get("reason", ""), reversed_by=request.user)
        return Response(self.get_serializer(reversed_payment).data)


class FinancialLedgerEntryViewSet(SchoolScopedQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = FinancialLedgerEntry.objects.all()
    serializer_class = FinancialLedgerEntrySerializer
    school_lookup = "student__school_class__school"
    permission_classes = [IsSchoolAdministrator]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("student", "fee_assignment", "payment")
        if student := self.request.query_params.get("student"):
            queryset = queryset.filter(student_id=student)
        return queryset.order_by("occurred_at", "id")


class ReceiptViewSet(SchoolScopedQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Receipt.objects.all()
    serializer_class = ReceiptSerializer
    school_lookup = "payment__student_fee_assignment__student__school_class__school"
    permission_classes = [IsSchoolAdministrator]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("payment__student_fee_assignment__student", "payment__student_fee_assignment__fee")
        if student := self.request.query_params.get("student"):
            queryset = queryset.filter(payment__student_fee_assignment__student_id=student)
        return queryset.order_by("-issued_at", "-id")

    @action(detail=True, methods=["get"])
    def pdf(self, request, *args, **kwargs):
        return receipt_pdf_response(self.get_object())


class RecurringFeeTemplateViewSet(SchoolAdminViewSet):
    queryset = RecurringFeeTemplate.objects.all()
    serializer_class = RecurringFeeTemplateSerializer
    school_lookup = "school"

    def perform_create(self, serializer):
        serializer.save(school=self.get_school(), currency=serializer.validated_data.get("currency", self.get_school().default_currency))

    @action(detail=False, methods=["post"])
    def generate(self, request):
        month = request.data.get("month")
        if not month:
            raise ValidationError({"month": "A month in YYYY-MM-DD format is required."})
        from django.utils.dateparse import parse_date
        value = parse_date(month)
        if not value:
            raise ValidationError({"month": "Use a valid date."})
        return Response(generate_recurring_charges(school=self.get_school(), for_month=value))


def finance_summary(student):
    charges, payments, balance = student_totals(student)
    assignments = StudentFeeAssignment.objects.filter(student=student).select_related("fee", "student__school_class")
    assignment_data = []
    for assignment in assignments:
        owed, paid, outstanding = assignment_totals(assignment)
        assignment_data.append({
            **StudentFeeAssignmentSerializer(assignment, context={"school": student.school}).data,
            "total_paid": paid,
            "outstanding": outstanding,
        })
    payments_qs = Payment.objects.filter(student_fee_assignment__student=student).select_related("student_fee_assignment__student", "student_fee_assignment__fee", "receipt").order_by("-paid_at", "-id")
    receipts_qs = Receipt.objects.filter(payment__student_fee_assignment__student=student).select_related("payment__student_fee_assignment__student", "payment__student_fee_assignment__fee").order_by("-issued_at", "-id")
    entries = FinancialLedgerEntry.objects.filter(student=student).select_related("student", "fee_assignment", "payment").order_by("occurred_at", "id")
    running = Decimal("0.00")
    ledger = []
    for entry in entries:
        running += entry.amount if entry.entry_type == FinancialLedgerEntry.EntryType.CHARGE else -entry.amount if entry.entry_type == FinancialLedgerEntry.EntryType.PAYMENT else Decimal("0.00")
        ledger.append({**FinancialLedgerEntrySerializer(entry, context={"school": student.school}).data, "balance": running})
    return {
        "student": {"id": student.id, "display_name": f"{student.first_name} {student.last_name}".strip(), "admission_number": student.admission_number, "class_name": student.school_class.name},
        "currency": student.school.default_currency,
        "total_charges": charges,
        "total_payments": payments,
        "outstanding_balance": balance,
        "assignments": assignment_data,
        "payments": PaymentSerializer(payments_qs, many=True, context={"school": student.school}).data,
        "receipts": ReceiptSerializer(receipts_qs, many=True, context={"school": student.school}).data,
        "ledger": ledger,
    }


class SchoolFinanceBalancesView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request):
        school = request.user.school_administrator.school
        students = Student.objects.filter(school=school).select_related("school_class").order_by("last_name", "first_name", "id")
        if school_class := request.query_params.get("school_class"):
            students = students.filter(school_class_id=school_class)
        rows = []
        for student in students:
            charges, payments, balance = student_totals(student)
            rows.append({"id": student.id, "display_name": f"{student.first_name} {student.last_name}".strip(), "admission_number": student.admission_number, "class_name": student.school_class.name, "currency": school.default_currency, "total_charges": charges, "total_payments": payments, "outstanding_balance": balance})
        return Response(rows)


class SchoolStudentFinanceView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get(self, request, student_id):
        student = get_object_or_404(Student.objects.select_related("school_class"), pk=student_id, school=request.user.school_administrator.school)
        return Response(finance_summary(student))


class ParentStudentFinanceView(APIView):
    permission_classes = [IsParent]

    def get(self, request, student_id):
        student = get_object_or_404(Student.objects.select_related("school_class"), pk=student_id, parent_links__parent=request.user.parent_profile)
        return Response(finance_summary(student))


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

    @action(detail=True, methods=["get"])
    def pdf(self, request, *args, **kwargs):
        return receipt_pdf_response(self.get_object())


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
