from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    AcademicResultViewSet,
    AcademicYearViewSet,
    AvailableParentView,
    ClassSubjectViewSet,
    CurrentUserView,
    FeeViewSet,
    FinancialLedgerEntryViewSet,
    NotificationViewSet,
    ParentAcademicResultViewSet,
    ParentPaymentViewSet,
    ParentReceiptViewSet,
    ParentReportCardViewSet,
    ParentStudentViewSet,
    PaymentViewSet,
    PlatformSchoolViewSet,
    ReceiptViewSet,
    ReportCardViewSet,
    SchoolClassViewSet,
    SchoolParentStudentViewSet,
    SchoolProfileView,
    SchoolSearchView,
    StudentEnrollmentViewSet,
    StudentFeeAssignmentViewSet,
    StudentViewSet,
    SubjectViewSet,
    TermViewSet,
)

router = DefaultRouter()
router.register("platform/schools", PlatformSchoolViewSet, basename="platform-school")
router.register("school/classes", SchoolClassViewSet, basename="school-class")
router.register("school/students", StudentViewSet, basename="school-student")
router.register("school/academic-years", AcademicYearViewSet, basename="school-academic-year")
router.register("school/terms", TermViewSet, basename="school-term")
router.register("school/subjects", SubjectViewSet, basename="school-subject")
router.register("school/class-subjects", ClassSubjectViewSet, basename="school-class-subject")
router.register("school/enrollments", StudentEnrollmentViewSet, basename="school-enrollment")
router.register("school/fees", FeeViewSet, basename="school-fee")
router.register("school/fee-assignments", StudentFeeAssignmentViewSet, basename="school-fee-assignment")
router.register("school/payments", PaymentViewSet, basename="school-payment")
router.register("school/ledger", FinancialLedgerEntryViewSet, basename="school-ledger")
router.register("school/receipts", ReceiptViewSet, basename="school-receipt")
router.register("school/results", AcademicResultViewSet, basename="school-result")
router.register("school/report-cards", ReportCardViewSet, basename="school-report-card")
router.register("school/notifications", NotificationViewSet, basename="school-notification")
router.register("school/parent-links", SchoolParentStudentViewSet, basename="school-parent-link")
router.register("parent/students", ParentStudentViewSet, basename="parent-student")
router.register("parent/payments", ParentPaymentViewSet, basename="parent-payment")
router.register("parent/receipts", ParentReceiptViewSet, basename="parent-receipt")
router.register("parent/results", ParentAcademicResultViewSet, basename="parent-result")
router.register("parent/report-cards", ParentReportCardViewSet, basename="parent-report-card")

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("school/profile/", SchoolProfileView.as_view(), name="school-profile"),
    path("school/search/", SchoolSearchView.as_view(), name="school-search"),
    path("school/available-parents/", AvailableParentView.as_view(), name="school-available-parents"),
    path("", include(router.urls)),
]
