"""Only explicit public create endpoints bypass MTM authentication."""
from uuid import UUID
from django.conf import settings
from django.db import DatabaseError
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .permissions import IsSchoolAdministrator
from .tenant import SchoolScopedQuerysetMixin
from .intake_models import AdmissionApplication, ContactEnquiry
from .intake_serializers import ApplicationInput, EnquiryInput, ApplicationDetail, EnquiryDetail, ApplicationReview, EnquiryReview
from .intake_security import BoundedJSONParser, public_school, client_ip, consume_quotas, IntakeUnavailable
from .intake_services import submit, review


class PublicIntake(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []  # Atomic DB counters below are shared across every worker.
    parser_classes = [BoundedJSONParser]
    http_method_names = ["post", "options"]

    def post(self, request):
        try:
            school = public_school(request)
            consume_quotas([("ip", f"{school.pk}:{client_ip(request)}", settings.MTM_INTAKE_IP_LIMIT, 3600), ("school", str(school.pk), settings.MTM_INTAKE_SCHOOL_LIMIT, 3600)])
            try:
                operation_id = UUID(request.headers.get("Idempotency-Key", ""))
            except (ValueError, TypeError, AttributeError):
                raise ValidationError({"detail": "A UUID Idempotency-Key header is required."})
            serializer = self.input_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            result, created = submit(self.kind, school, operation_id, serializer.validated_data)
            return Response(result, status=201 if created else 200, headers={"Cache-Control": "no-store"})
        except DatabaseError:
            raise IntakeUnavailable() from None


class PublicApplication(PublicIntake):
    kind = "application"
    input_class = ApplicationInput


class PublicEnquiry(PublicIntake):
    kind = "enquiry"
    input_class = EnquiryInput


class IntakePagination(PageNumberPagination):
    page_size = 25
    max_page_size = 100


class SchoolIntake(SchoolScopedQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsSchoolAdministrator]
    pagination_class = IntakePagination
    http_method_names = ["get", "post", "head", "options"]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        return response

    def get_queryset(self):
        rows = super().get_queryset().order_by("-created_at", "id")
        if value := self.request.query_params.get("status"):
            rows = rows.filter(status=value)
        return rows

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        self.get_object()  # Resolve through the scoped queryset, never an unscoped ID.
        serializer = self.review_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = review(self.kind, self.get_school(), request.user, pk, serializer.validated_data)
        except DatabaseError:
            raise IntakeUnavailable() from None
        return Response(self.get_serializer(record).data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        record = self.get_object()
        rows = record.history.all()
        page = self.paginate_queryset(rows)
        fields = ["id", "actor_id", "from_status", "to_status", "note", "version", "created_at"]
        if self.kind == "enquiry":
            fields.append("assigned_administrator_id")
        data = [{key: getattr(row, key) for key in fields} for row in (page if page is not None else rows)]
        return self.get_paginated_response(data) if page is not None else Response(data)


class SchoolApplications(SchoolIntake):
    kind = "application"
    queryset = AdmissionApplication.objects.all()
    serializer_class = ApplicationDetail
    review_class = ApplicationReview


class SchoolEnquiries(SchoolIntake):
    kind = "enquiry"
    queryset = ContactEnquiry.objects.all()
    serializer_class = EnquiryDetail
    review_class = EnquiryReview
