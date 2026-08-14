from datetime import timedelta
from secrets import compare_digest

from django.conf import settings
from decimal import Decimal

from django.db import transaction
from django.db import connection
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    AcademicResult,
    AcademicYear,
    AuditLog,
    Announcement,
    ClassSubject,
    CommunicationMessage,
    Fee,
    FinancialLedgerEntry,
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
)
from .finance import assign_fee, assignment_totals, generate_recurring_charges, record_payment, reverse_payment, student_totals
from .communications import (
    announcement_recipients,
    claim_whatsapp_messages,
    communication_settings,
    create_fee_reminders,
    create_report_card_messages,
    send_announcement,
    transition_message,
)
from .audit import log_action
from .permissions import IsParent, IsPlatformAdministrator, IsSchoolAdministrator
from .serializers import (
    AcademicResultSerializer,
    AcademicYearSerializer,
    AuditLogSerializer,
    AnnouncementSerializer,
    AvailableParentSerializer,
    ClassSubjectSerializer,
    CommunicationMessageSerializer,
    CurrentUserSerializer,
    FeeSerializer,
    FinancialLedgerEntrySerializer,
    NotificationSerializer,
    ParentPaymentSerializer,
    ParentCommunicationPreferenceSerializer,
    ParentDetailSerializer,
    ParentListSerializer,
    ParentWriteSerializer,
    ParentReceiptSerializer,
    ParentReportCardSerializer,
    ParentNotificationSerializer,
    ParentResultSerializer,
    ParentStudentSerializer,
    PaymentSerializer,
    ReceiptSerializer,
    RecurringFeeTemplateSerializer,
    ReportCardSerializer,
    SchoolClassSerializer,
    SchoolCommunicationSettingsSerializer,
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


class LoginTokenObtainPairView(TokenObtainPairView):
    throttle_scope = "login"
    throttle_classes = [ScopedRateThrottle]


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
        school = serializer.save()
        log_action(school=school, actor=request.user, action="school_profile_updated", resource=school, description="School profile settings updated")
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


class SchoolCommunicationSettingsView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get_object(self, request):
        return communication_settings(request.user.school_administrator.school)

    def get(self, request):
        return Response(SchoolCommunicationSettingsSerializer(self.get_object(request)).data)

    def patch(self, request):
        serializer = SchoolCommunicationSettingsSerializer(self.get_object(request), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        settings_object = serializer.save()
        log_action(school=settings_object.school, actor=request.user, action="communication_settings_updated", resource=settings_object, description="Communication settings updated")
        return Response(serializer.data)


class AnnouncementViewSet(SchoolAdminViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    school_lookup = "school"

    def get_queryset(self):
        return super().get_queryset().select_related("school_class", "student", "parent", "created_by").order_by("-created_at", "-id")

    def perform_create(self, serializer):
        serializer.save(school=self.get_school(), created_by=self.request.user)

    def perform_update(self, serializer):
        if self.get_object().status != Announcement.Status.DRAFT:
            raise ValidationError({"detail": "Sent announcements are immutable."})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        if self.get_object().status != Announcement.Status.DRAFT:
            raise MethodNotAllowed("DELETE")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def preview(self, request, *args, **kwargs):
        announcement = self.get_object()
        return Response({"recipient_count": announcement_recipients(announcement).count(), "status": announcement.status})

    @action(detail=True, methods=["post"])
    def send(self, request, *args, **kwargs):
        if request.data.get("confirm") is not True:
            raise ValidationError({"confirm": "Set confirm to true after reviewing the recipient count."})
        announcement, recipient_count = send_announcement(self.get_object())
        log_action(school=announcement.school, actor=request.user, action="announcement_sent", resource=announcement, description=f"Announcement sent to {recipient_count} parent(s)")
        return Response({"id": announcement.id, "status": announcement.status, "recipient_count": recipient_count})


class CommunicationMessageViewSet(SchoolScopedQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = CommunicationMessage.objects.all()
    serializer_class = CommunicationMessageSerializer
    school_lookup = "school"
    permission_classes = [IsSchoolAdministrator]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("parent__user", "student", "notification")
        for param in ("status", "channel", "event_type"):
            if value := self.request.query_params.get(param):
                queryset = queryset.filter(**{param: value})
        if value := self.request.query_params.get("student"):
            queryset = queryset.filter(student_id=value)
        if value := self.request.query_params.get("parent"):
            queryset = queryset.filter(parent_id=value)
        if value := self.request.query_params.get("date"):
            queryset = queryset.filter(created_at__date=value)
        return queryset.order_by("-created_at", "-id")


class AuditLogViewSet(SchoolScopedQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    school_lookup = "school"
    permission_classes = [IsSchoolAdministrator]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("actor")
        if value := self.request.query_params.get("actor"):
            queryset = queryset.filter(actor_id=value)
        if value := self.request.query_params.get("action"):
            queryset = queryset.filter(action=value)
        if value := self.request.query_params.get("resource_type"):
            queryset = queryset.filter(resource_type=value)
        if value := self.request.query_params.get("date"):
            queryset = queryset.filter(created_at__date=value)
        return queryset


class SchoolParentCommunicationPreferenceView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def get_object(self, request, parent_id):
        parent = get_object_or_404(Parent, pk=parent_id, school=request.user.school_administrator.school)
        preference, _ = ParentCommunicationPreference.objects.get_or_create(parent=parent)
        return preference

    def get(self, request, parent_id):
        preference = self.get_object(request, parent_id)
        return Response(ParentCommunicationPreferenceSerializer(preference, context={"parent": preference.parent}).data)

    def patch(self, request, parent_id):
        preference = self.get_object(request, parent_id)
        if preference.whatsapp_status == ParentCommunicationPreference.WhatsAppStatus.OPTED_OUT and request.data.get("whatsapp_status") == ParentCommunicationPreference.WhatsAppStatus.OPTED_IN:
            raise ValidationError({"whatsapp_status": "A parent opt-out cannot be overridden by a school administrator."})
        serializer = ParentCommunicationPreferenceSerializer(preference, data=request.data, partial=True, context={"parent": preference.parent})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SchoolFeeReminderView(APIView):
    permission_classes = [IsSchoolAdministrator]

    def post(self, request):
        school = request.user.school_administrator.school
        requested_ids = request.data.get("student_ids", [])
        if requested_ids and (not isinstance(requested_ids, list) or not all(isinstance(value, int) for value in requested_ids)):
            raise ValidationError({"student_ids": "Use a list of student IDs from this school."})
        students = Student.objects.filter(school=school, is_active=True)
        if requested_ids:
            students = students.filter(id__in=requested_ids)
            if students.count() != len(set(requested_ids)):
                raise ValidationError({"student_ids": "One or more students do not belong to this school."})
        return Response(create_fee_reminders(school=school, students=students))


class ParentCommunicationPreferenceView(APIView):
    permission_classes = [IsParent]

    def get_object(self, request):
        preference, _ = ParentCommunicationPreference.objects.get_or_create(parent=request.user.parent_profile)
        return preference

    def get(self, request):
        preference = self.get_object(request)
        return Response(ParentCommunicationPreferenceSerializer(preference, context={"parent": preference.parent}).data)

    def patch(self, request):
        preference = self.get_object(request)
        serializer = ParentCommunicationPreferenceSerializer(preference, data=request.data, partial=True, context={"parent": preference.parent})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ParentNotificationViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    permission_classes = [IsParent]
    serializer_class = ParentNotificationSerializer

    def get_queryset(self):
        parent = self.request.user.parent_profile
        return Notification.objects.filter(school=parent.school, recipient=self.request.user).select_related("student").order_by("-created_at", "-id")

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, *args, **kwargs):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)


class N8NIntegrationView(APIView):
    """Separate shared-secret boundary for n8n; JWT roles never authorize it."""

    permission_classes = []
    throttle_scope = "integration"
    throttle_classes = [ScopedRateThrottle]

    def is_authorized(self, request):
        configured = getattr(settings, "MTM_N8N_INTEGRATION_SECRET", "")
        presented = request.headers.get("X-MTM-Integration-Secret", "")
        return bool(configured and presented and compare_digest(configured, presented))

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not self.is_authorized(request):
            raise PermissionDenied("A valid integration credential is required.")


def integration_message_payload(message):
    return {
        "id": message.id,
        "event_type": message.event_type,
        "template_key": message.template_key,
        "recipient": message.payload.get("recipient"),
        "language": "en",
        "parameters": {key: value for key, value in message.payload.items() if key != "recipient"},
        "has_attachment": bool(message.receipt_id),
    }


class N8NOutboxClaimView(N8NIntegrationView):
    def post(self, request):
        try:
            batch_size = min(max(int(request.data.get("batch_size", 10)), 1), 50)
        except (TypeError, ValueError):
            raise ValidationError({"batch_size": "Use a whole number between 1 and 50."})
        messages = claim_whatsapp_messages(
            batch_size=batch_size,
            stale_after_seconds=getattr(settings, "MTM_OUTBOX_CLAIM_TIMEOUT_SECONDS", 900),
            max_attempts=getattr(settings, "MTM_OUTBOX_MAX_ATTEMPTS", 5),
        )
        return Response({"messages": [integration_message_payload(message) for message in messages]})


class N8NOutboxSentView(N8NIntegrationView):
    def post(self, request, message_id):
        message = get_object_or_404(CommunicationMessage, pk=message_id, channel=CommunicationMessage.Channel.WHATSAPP)
        provider_message_id = str(request.data.get("provider_message_id", "")).strip()
        if not provider_message_id:
            raise ValidationError({"provider_message_id": "The provider message ID is required."})
        if CommunicationMessage.objects.exclude(pk=message.pk).filter(provider_message_id=provider_message_id).exists():
            raise ValidationError({"provider_message_id": "This provider message ID is already recorded."})
        transition_message(message, CommunicationMessage.Status.SENT, provider_message_id=provider_message_id)
        return Response({"id": message.id, "status": message.status})


class N8NOutboxFailedView(N8NIntegrationView):
    def post(self, request, message_id):
        message = get_object_or_404(CommunicationMessage, pk=message_id, channel=CommunicationMessage.Channel.WHATSAPP)
        reason = str(request.data.get("reason", "Delivery failed")).strip()[:255]
        transition_message(message, CommunicationMessage.Status.FAILED, failure_reason=reason or "Delivery failed")
        return Response({"id": message.id, "status": message.status})


class N8NWhatsAppStatusView(N8NIntegrationView):
    def post(self, request):
        provider_message_id = str(request.data.get("provider_message_id", "")).strip()
        new_status = str(request.data.get("status", "")).strip().lower()
        allowed = {
            "sent": CommunicationMessage.Status.SENT,
            "delivered": CommunicationMessage.Status.DELIVERED,
            "read": CommunicationMessage.Status.READ,
            "failed": CommunicationMessage.Status.FAILED,
        }
        if not provider_message_id or new_status not in allowed:
            raise ValidationError({"detail": "A provider_message_id and a valid status are required."})
        message = CommunicationMessage.objects.filter(provider_message_id=provider_message_id, channel=CommunicationMessage.Channel.WHATSAPP).first()
        if not message:
            return Response({"updated": False})
        transition_message(message, allowed[new_status], failure_reason=str(request.data.get("reason", ""))[:255])
        return Response({"updated": True, "id": message.id, "status": message.status})


class N8NOutboxAttachmentView(N8NIntegrationView):
    def get(self, request, message_id):
        message = get_object_or_404(
            CommunicationMessage.objects.select_related("receipt__payment__student_fee_assignment__student"),
            pk=message_id,
            channel=CommunicationMessage.Channel.WHATSAPP,
            event_type=CommunicationMessage.EventType.PAYMENT_RECEIPT,
            receipt__isnull=False,
        )
        return receipt_pdf_response(message.receipt)


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
            log_action(school=student.school, actor=self.request.user, action="student_created", resource=student, description="Student record created")

    def perform_update(self, serializer):
        student = serializer.save()
        log_action(school=student.school, actor=self.request.user, action="student_updated", resource=student, description="Student record updated")

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
        log_action(school=student.school, actor=request.user, action="student_transferred", resource=student, description=f"Transferred to {next_class.name}")
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
        parent = serializer.save()
        log_action(school=parent.school, actor=self.request.user, action="parent_created", resource=parent, description="Parent account created")

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
        parent = serializer.save()
        log_action(school=parent.school, actor=request.user, action="parent_updated", resource=parent, description="Parent record updated")
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
        fee = serializer.save(school=self.get_school(), currency=serializer.validated_data.get("currency", self.get_school().default_currency))
        log_action(school=fee.school, actor=self.request.user, action="fee_created", resource=fee, description="Fee created")

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
        log_action(school=assignment.student.school, actor=request.user, action="fee_assigned", resource=assignment, description="Fee assigned to student")
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
        log_action(school=payment.student_fee_assignment.student.school, actor=request.user, action="payment_recorded", resource=payment, description=f"Receipt {receipt.receipt_number} created")
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
        log_action(school=reversed_payment.student_fee_assignment.student.school, actor=request.user, action="payment_reversed", resource=reversed_payment, description="Payment reversed")
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
        result = serializer.save(recorded_by=self.request.user)
        log_action(school=result.student_enrollment.student.school, actor=self.request.user, action="result_recorded", resource=result, description="Academic result recorded")

    def perform_update(self, serializer):
        result = serializer.save()
        log_action(school=result.student_enrollment.student.school, actor=self.request.user, action="result_updated", resource=result, description="Academic result updated")

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

    @action(detail=True, methods=["post"], url_path="notify-parents")
    def notify_parents(self, request, *args, **kwargs):
        report_card = self.get_object()
        messages = create_report_card_messages(report_card)
        log_action(school=report_card.student_enrollment.student.school, actor=request.user, action="report_card_notified", resource=report_card, description=f"Created {len(messages)} communication record(s)")
        return Response({"report_card": report_card.id, "messages_created": len(messages)})


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

    def perform_create(self, serializer):
        link = serializer.save()
        log_action(school=link.student.school, actor=self.request.user, action="parent_linked", resource=link, description="Parent linked to student")


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


class HealthView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok", "version": getattr(settings, "MTM_APP_VERSION", "5.8")})


class ReadinessView(HealthView):
    def get(self, request):
        try:
            connection.ensure_connection()
        except Exception:
            return Response({"status": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})
