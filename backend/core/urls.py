from .intake_api import PublicApplication, PublicEnquiry, SchoolApplications, SchoolEnquiries
from .reporting_api import AttendanceHistoryView, SchoolAccountStatementView, ParentAccountStatementView
from .finance_documents import DocumentSettingsView, DebtorsView, InvoiceView
from .academic_history import AcademicHistoryView
from .academics_api import TimetableViewSet
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    AcademicResultViewSet,
    AcademicYearViewSet,
    AuditLogViewSet,
    AnnouncementViewSet,
    AttendanceBulkView,
    AttendanceRosterView,
    AvailableParentView,
    ClassSubjectViewSet,
    CommunicationMessageViewSet,
    CurrentUserView,
    LoginTokenObtainPairView,
    HealthView,
    HomeworkViewSet,
    InventoryCategoryViewSet,
    InventoryItemViewSet,
    InventoryStockMovementViewSet,
    InventorySummaryView,
    InventoryVariantViewSet,
    ReadinessView,
    FeeViewSet,
    ExpenseViewSet,
    FinancialLedgerEntryViewSet,
    NotificationViewSet,
    N8NOutboxAttachmentView,
    N8NOutboxClaimView,
    N8NOutboxFailedView,
    N8NOutboxSentView,
    N8NWhatsAppStatusView,
    ParentAcademicResultViewSet,
    ParentHomeworkViewSet,
    ParentCommunicationPreferenceView,
    ParentNotificationViewSet,
    ParentStudentTimetableView,
    ParentViewSet,
    ParentPaymentViewSet,
    ParentReceiptViewSet,
    ParentReportCardViewSet,
    ParentStudentViewSet,
    PaymentViewSet,
    PlatformSchoolViewSet,
    PlatformDashboardView,
    PlatformAuditView,
    PlatformSchoolAdministratorsView,
    PlatformSchoolAdministratorActionView,
    PasswordChangeView,
    MTMTokenRefreshView,
    ReceiptViewSet,
    RecurringFeeTemplateViewSet,
    ReportCardViewSet,
    SchoolClassViewSet,
    SchoolCommunicationSettingsView,
    SchoolFeeReminderView,
    SchoolParentCommunicationPreferenceView,
    SchoolParentStudentViewSet,
    SchoolProfileView,
    SchoolSearchView,
    SchoolFinanceBalancesView,
    SchoolDailyCashbookView,
    SchoolStudentFinanceView,
    StudentEnrollmentViewSet,
    StudentFeeAssignmentViewSet,
    StudentViewSet,
    SubjectViewSet,
    TermViewSet,
    TimetableEntryViewSet,
    ParentStudentFinanceView,
)

router = DefaultRouter()
from .staff_api import TeacherManagement, TeacherLookups, TeacherStudents, TeacherHomework, ResultWorkflow, TeacherComments, StaffAnnouncements, TeacherResources, TeacherTimetable
from .password_recovery import ForgotPassword, ResetPassword
from .school_finance_api import (SchoolFinancialReportView, FinanceLookupsView, FinanceConfigurationViewSet,
    FinanceCategoryViewSet, OtherIncomeViewSet, SchoolExpenseViewSet, FinancialReportNoteView)
from .attendance_register import AttendanceRegister
from .staff_api import TeacherCatalog
router.register("school/teachers", TeacherManagement, basename="school-teacher")
router.register("teacher/students", TeacherStudents, basename="teacher-student")
router.register("teacher/homework", TeacherHomework, basename="teacher-homework")
router.register("teacher/results", ResultWorkflow, basename="teacher-result")
router.register("school/result-review", ResultWorkflow, basename="school-result-review")
router.register("teacher/comments", TeacherComments, basename="teacher-comment")
router.register("teacher/announcements", StaffAnnouncements, basename="teacher-announcement")
router.register("school/teacher-announcements", StaffAnnouncements, basename="school-teacher-announcement")
router.register("teacher/resources", TeacherResources, basename="teacher-resource")
router.register("teacher/timetable", TeacherTimetable, basename="teacher-timetable")
router.register("school/applications", SchoolApplications, basename="school-application")
router.register("school/enquiries", SchoolEnquiries, basename="school-enquiry")
router.register("platform/schools", PlatformSchoolViewSet, basename="platform-school")
router.register("school/classes", SchoolClassViewSet, basename="school-class")
router.register("school/students", StudentViewSet, basename="school-student")
router.register("school/parents", ParentViewSet, basename="school-parent")
router.register("school/academic-years", AcademicYearViewSet, basename="school-academic-year")
router.register("school/terms", TermViewSet, basename="school-term")
router.register("school/subjects", SubjectViewSet, basename="school-subject")
router.register("school/class-subjects", ClassSubjectViewSet, basename="school-class-subject")
router.register("school/enrollments", StudentEnrollmentViewSet, basename="school-enrollment")
router.register("school/fees", FeeViewSet, basename="school-fee")
router.register("school/expenses", SchoolExpenseViewSet, basename="school-expense")
router.register("school/finance/accounts", FinanceConfigurationViewSet, basename="school-finance-account")
router.register("school/finance/categories", FinanceCategoryViewSet, basename="school-finance-category")
router.register("school/finance/other-income", OtherIncomeViewSet, basename="school-other-income")
router.register("school/fee-assignments", StudentFeeAssignmentViewSet, basename="school-fee-assignment")
router.register("school/payments", PaymentViewSet, basename="school-payment")
router.register("school/ledger", FinancialLedgerEntryViewSet, basename="school-ledger")
router.register("school/receipts", ReceiptViewSet, basename="school-receipt")
router.register("school/recurring-fees", RecurringFeeTemplateViewSet, basename="school-recurring-fee")
router.register("school/results", ResultWorkflow, basename="school-result")
router.register("school/report-cards", ReportCardViewSet, basename="school-report-card")
router.register("school/notifications", NotificationViewSet, basename="school-notification")
router.register("school/communication/announcements", AnnouncementViewSet, basename="school-announcement")
router.register("school/communication/history", CommunicationMessageViewSet, basename="school-communication-history")
router.register("school/audit", AuditLogViewSet, basename="school-audit")
router.register("school/parent-links", SchoolParentStudentViewSet, basename="school-parent-link")
router.register("school/timetable-plans", TimetableViewSet, basename="school-timetable-plan")
router.register("school/timetables", TimetableEntryViewSet, basename="school-timetable")
router.register("school/homework", HomeworkViewSet, basename="school-homework")
router.register("school/inventory/categories", InventoryCategoryViewSet, basename="school-inventory-category")
router.register("school/inventory/items", InventoryItemViewSet, basename="school-inventory-item")
router.register("school/inventory/variants", InventoryVariantViewSet, basename="school-inventory-variant")
router.register("school/inventory/movements", InventoryStockMovementViewSet, basename="school-inventory-movement")
router.register("parent/students", ParentStudentViewSet, basename="parent-student")
router.register("parent/payments", ParentPaymentViewSet, basename="parent-payment")
router.register("parent/receipts", ParentReceiptViewSet, basename="parent-receipt")
router.register("parent/results", ParentAcademicResultViewSet, basename="parent-result")
router.register("parent/report-cards", ParentReportCardViewSet, basename="parent-report-card")
router.register("parent/notifications", ParentNotificationViewSet, basename="parent-notification")
router.register("parent/homework", ParentHomeworkViewSet, basename="parent-homework")

urlpatterns = [
    path('school/finance/lookups/', FinanceLookupsView.as_view()),
    path('school/finance/report-notes/', FinancialReportNoteView.as_view()),
    path('school/finance/reports/<str:report>/', SchoolFinancialReportView.as_view()),
    path("school/document-settings/", DocumentSettingsView.as_view()),
    path("school/finance/ageing/", DebtorsView.as_view()),
    path("school/finance/outstanding/", DebtorsView.as_view(), {'outstanding': True}),
    path("school/finance/invoices/", InvoiceView.as_view()),
    path("school/finance/invoices/<int:invoice_id>/", InvoiceView.as_view()),
    path("parent/invoices/", InvoiceView.as_view()),
    path("parent/invoices/<int:invoice_id>/", InvoiceView.as_view()),
    path("school/students/<int:student_id>/academic-history/", AcademicHistoryView.as_view()),
    path("teacher/students/<int:student_id>/academic-history/", AcademicHistoryView.as_view()),
    path("parent/students/<int:student_id>/academic-history/", AcademicHistoryView.as_view()),
    path("teacher/catalog/<str:resource>/", TeacherCatalog.as_view()),
    path("school/attendance/register/", AttendanceRegister.as_view()),
    path("teacher/lookups/", TeacherLookups.as_view()),
    path("auth/forgot-password/", ForgotPassword.as_view()),
    path("auth/reset-password/", ResetPassword.as_view()),
    path("public/beavers/applications/", PublicApplication.as_view(), name="beavers-applications"),
    path("public/beavers/enquiries/", PublicEnquiry.as_view(), name="beavers-enquiries"),
    path("school/attendance/history/", AttendanceHistoryView.as_view()),
    path("school/finance/students/<int:student_id>/statement/", SchoolAccountStatementView.as_view()),
    path("parent/students/<int:student_id>/statement/", ParentAccountStatementView.as_view()),
    path("health/", HealthView.as_view(), name="health"),
    path("health/ready/", ReadinessView.as_view(), name="health-ready"),
    path("auth/token/", LoginTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/token/refresh/", MTMTokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("auth/change-password/", PasswordChangeView.as_view(), name="change-password"),
    path("platform/dashboard/", PlatformDashboardView.as_view(), name="platform-dashboard"),
    path("platform/audit/", PlatformAuditView.as_view(), name="platform-audit"),
    path("platform/schools/<int:school_id>/administrators/", PlatformSchoolAdministratorsView.as_view(), name="platform-school-administrators"),
    path("platform/schools/<int:school_id>/administrators/<int:administrator_id>/<str:operation>/", PlatformSchoolAdministratorActionView.as_view(), name="platform-school-administrator-action"),
    path("school/profile/", SchoolProfileView.as_view(), name="school-profile"),
    path("school/search/", SchoolSearchView.as_view(), name="school-search"),
    path("school/available-parents/", AvailableParentView.as_view(), name="school-available-parents"),
    path("school/finance/balances/", SchoolFinanceBalancesView.as_view(), name="school-finance-balances"),
    path("school/finance/cashbook/", SchoolDailyCashbookView.as_view(), name="school-finance-cashbook"),
    path("school/inventory/summary/", InventorySummaryView.as_view(), name="school-inventory-summary"),
    path("school/attendance/roster/", AttendanceRosterView.as_view(), name="school-attendance-roster"),
    path("school/attendance/bulk/", AttendanceBulkView.as_view(), name="school-attendance-bulk"),
    path("school/finance/students/<int:student_id>/", SchoolStudentFinanceView.as_view(), name="school-student-finance"),
    path("school/communication/settings/", SchoolCommunicationSettingsView.as_view(), name="school-communication-settings"),
    path("school/communication/fee-reminders/", SchoolFeeReminderView.as_view(), name="school-fee-reminders"),
    path("school/communication/parents/<int:parent_id>/preference/", SchoolParentCommunicationPreferenceView.as_view(), name="school-parent-communication-preference"),
    path("parent/students/<int:student_id>/timetable/", ParentStudentTimetableView.as_view(), name="parent-student-timetable"),
    path("parent/students/<int:student_id>/finance/", ParentStudentFinanceView.as_view(), name="parent-student-finance"),
    path("parent/communication/preference/", ParentCommunicationPreferenceView.as_view(), name="parent-communication-preference"),
    path("integrations/n8n/outbox/claim/", N8NOutboxClaimView.as_view(), name="n8n-outbox-claim"),
    path("integrations/n8n/outbox/<int:message_id>/sent/", N8NOutboxSentView.as_view(), name="n8n-outbox-sent"),
    path("integrations/n8n/outbox/<int:message_id>/failed/", N8NOutboxFailedView.as_view(), name="n8n-outbox-failed"),
    path("integrations/n8n/outbox/<int:message_id>/attachment/", N8NOutboxAttachmentView.as_view(), name="n8n-outbox-attachment"),
    path("integrations/n8n/whatsapp/status/", N8NWhatsAppStatusView.as_view(), name="n8n-whatsapp-status"),
    path("", include(router.urls)),
]
