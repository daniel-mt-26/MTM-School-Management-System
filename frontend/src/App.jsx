import AccountStatementPage from './pages/AccountStatementPage'
import SchoolFinancialPage from './pages/SchoolFinancialPage'
import SchoolExpensesPage from './pages/SchoolExpensesPage'
import FinanceConfigurationPage from './pages/FinanceConfigurationPage'
import InvoicesPage from './pages/InvoicesPage'
import DebtorsPage from './pages/DebtorsPage'
import StudentStatementsPage from './pages/StudentStatementsPage'
import AcademicHistoryPage from './pages/AcademicHistoryPage'
import TimetablesPage from './pages/TimetablesPage'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import ProtectedRoute from './auth/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import AcademicsPage from './pages/AcademicsPage'
import CommunicationPage from './pages/CommunicationPage'
import FinancePage from './pages/FinancePage'
import ParentDashboard from './pages/ParentDashboard'
import ParentsPage from './pages/ParentsPage'
import ParentDetailPage from './pages/ParentDetailPage'
import ParentFormPage from './pages/ParentFormPage'
import AcademicRecordsPage from './pages/AcademicRecordsPage'
import AuditPage from './pages/AuditPage'
import PlatformDashboard from './pages/PlatformDashboard'
import PlatformSchoolsPage from './pages/PlatformSchoolsPage'
import PlatformSchoolFormPage from './pages/PlatformSchoolFormPage'
import PlatformAuditPage from './pages/PlatformAuditPage'
import PlatformSchoolDetailPage from './pages/PlatformSchoolDetailPage'
import ChangePasswordPage from './pages/ChangePasswordPage'
import SchoolAccessBlockedPage from './pages/SchoolAccessBlockedPage'
import SchoolDashboard from './pages/SchoolDashboard'
import SchoolSettingsPage from './pages/SchoolSettingsPage'
import StudentsPage from './pages/StudentsPage'
import StudentDetailPage from './pages/StudentDetailPage'
import StudentFormPage from './pages/StudentFormPage'
import FeeManagementPage from './pages/FeeManagementPage'
import FinanceRecordsPage from './pages/FinanceRecordsPage'
import StudentFinancePage from './pages/StudentFinancePage'
import HomeworkPage from './pages/HomeworkPage'
import ParentHomeworkPage from './pages/ParentHomeworkPage'
import InventoryPage from './pages/InventoryPage'
import AttendancePage from './pages/AttendancePage'
import SchoolOfflineShell from './pages/SchoolOfflineShell'
import IntakeOnlineBoundary from './components/IntakeOnlineBoundary'
import IntakeListPage from './pages/IntakeListPage'
import IntakeDetailPage from './pages/IntakeDetailPage'
import PwaUpdatePrompt from './offline/PwaUpdatePrompt'
import TeacherPortal from './pages/TeacherPortal'
import TeachersPage from './pages/TeachersPage'
import TeacherAnnouncementsPage from './pages/TeacherAnnouncementsPage'
import ResultsReviewPage from './pages/ResultsReviewPage'
import PasswordRecoveryPage from './pages/PasswordRecoveryPage'
import Attribution from './components/Attribution'
import ParentReportsPage from './pages/ParentReportsPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<PasswordRecoveryPage />} />
          <Route path="/reset-password" element={<PasswordRecoveryPage reset />} />
          <Route element={<ProtectedRoute allowedRole="teacher" />}><Route element={<SchoolOfflineShell />}><Route path="/teacher" element={<TeacherPortal />} /><Route path="/teacher/:section" element={<TeacherPortal />} /></Route></Route>
          <Route element={<ProtectedRoute />}>
            <Route path="/change-password" element={<ChangePasswordPage />} />
            <Route path="/school-access-blocked" element={<SchoolAccessBlockedPage />} />
          </Route>
          <Route element={<ProtectedRoute allowedRole="teacher" />}><Route path="/teacher/students/:studentId/academic-history" element={<AcademicHistoryPage teacher />} /></Route>
          <Route element={<ProtectedRoute allowedRole="platform_admin" />}>
            <Route path="/platform" element={<PlatformDashboard />} />
            <Route path="/platform/schools" element={<PlatformSchoolsPage />} />
            <Route path="/platform/schools/new" element={<PlatformSchoolFormPage />} />
            <Route path="/platform/schools/:id" element={<PlatformSchoolDetailPage />} />
            <Route path="/platform/audit" element={<PlatformAuditPage />} />
          </Route>
          <Route element={<ProtectedRoute allowedRole="school_admin" />}>
            <Route element={<IntakeOnlineBoundary />}>
              <Route path="/school/admissions" element={<IntakeListPage key="applications" kind="applications" />} />
              <Route path="/school/admissions/:intakeId" element={<IntakeDetailPage key="applications" kind="applications" />} />
              <Route path="/school/enquiries" element={<IntakeListPage key="enquiries" kind="enquiries" />} />
              <Route path="/school/enquiries/:intakeId" element={<IntakeDetailPage key="enquiries" kind="enquiries" />} />
            </Route>
            <Route element={<SchoolOfflineShell />}>
            <Route path="/school/teachers" element={<TeachersPage />} />
            <Route path="/school/teacher-announcements" element={<TeacherAnnouncementsPage />} />
            <Route path="/school/result-review" element={<ResultsReviewPage />} />
            <Route path="/school" element={<SchoolDashboard />} />
            <Route path="/app" element={<SchoolDashboard />} />
            <Route path="/school/students" element={<StudentsPage />} />
            <Route path="/school/students/new" element={<StudentFormPage />} />
            <Route path="/school/students/:studentId" element={<StudentDetailPage />} />
            <Route path="/school/students/:studentId/edit" element={<StudentFormPage />} />
            <Route path="/school/parents" element={<ParentsPage />} />
            <Route path="/school/parents/new" element={<ParentFormPage />} />
            <Route path="/school/parents/:parentId" element={<ParentDetailPage />} />
            <Route path="/school/parents/:parentId/edit" element={<ParentFormPage />} />
            <Route path="/school/academics" element={<AcademicsPage />} />
            <Route path="/school/academics/homework" element={<HomeworkPage />} />
            <Route path="/school/academics/timetables" element={<TimetablesPage />} />
            <Route path="/school/academics/curriculum" element={<Navigate to="/school/academics" replace />} />
            <Route path="/school/academics/:resource" element={<AcademicRecordsPage />} />
            <Route path="/school/finance" element={<FinancePage />} />
            <Route path="/school/finance/income" element={<SchoolFinancialPage key="income" report="income" />} />
            <Route path="/school/finance/expenses" element={<SchoolExpensesPage />} />
            <Route path="/school/finance/cash-books" element={<SchoolFinancialPage key="cash-books" report="cash-books" />} />
            <Route path="/school/finance/monthly" element={<SchoolFinancialPage key="monthly" report="monthly" />} />
            <Route path="/school/finance/annual" element={<SchoolFinancialPage key="annual" report="annual" />} />
            <Route path="/school/finance/financial-dashboard" element={<SchoolFinancialPage key="dashboard" report="dashboard" />} />
            <Route path="/school/finance/cash-received" element={<SchoolFinancialPage key="cash-received" report="cash-received" />} />
            <Route path="/school/finance/expense-report" element={<SchoolFinancialPage key="expense-report" report="expense-report" />} />
            <Route path="/school/finance/configuration" element={<FinanceConfigurationPage />} />
            <Route path="/school/finance/fee-management" element={<FeeManagementPage key="structures" />} />
            <Route path="/school/finance/charges" element={<FeeManagementPage key="charges" initialTab="Charges" />} />
            <Route path="/school/finance/invoices" element={<InvoicesPage />} />
            <Route path="/school/finance/invoices/:invoiceId" element={<InvoicesPage />} />
            <Route path="/school/finance/statements" element={<StudentStatementsPage />} />
            <Route path="/school/finance/ageing" element={<DebtorsPage key="ageing" />} />
            <Route path="/school/finance/outstanding" element={<DebtorsPage key="outstanding" outstanding />} />
            <Route path="/school/academics/history" element={<AcademicHistoryPage />} />
            <Route path="/school/students/:studentId/academic-history" element={<AcademicHistoryPage />} />
            <Route path="/school/finance/:resource" element={<FinanceRecordsPage />} />
            <Route path="/school/finance/students/:studentId/statement" element={<AccountStatementPage />} />
            <Route path="/school/finance/students/:studentId" element={<StudentFinancePage />} />
            <Route path="/school/inventory" element={<InventoryPage />} />
            <Route path="/school/inventory/:section" element={<InventoryPage />} />
            <Route path="/school/attendance" element={<AttendancePage />} />
            <Route path="/school/communication" element={<CommunicationPage />} />
            <Route path="/school/communication/:section" element={<CommunicationPage />} />
            <Route path="/school/settings" element={<SchoolSettingsPage />} />
            <Route path="/school/audit" element={<AuditPage />} />
            </Route>
          </Route>
          <Route element={<ProtectedRoute allowedRole="parent" />}>
            <Route path="/parent" element={<ParentDashboard />} />
            <Route path="/parent/reports" element={<ParentReportsPage />} />
            <Route path="/parent/invoices" element={<InvoicesPage parent />} />
            <Route path="/parent/invoices/:invoiceId" element={<InvoicesPage parent />} />
            <Route path="/parent/students/:studentId/academic-history" element={<AcademicHistoryPage parent />} />
            <Route path="/parent/students/:studentId/statement" element={<AccountStatementPage parent />} />
            <Route path="/parent/homework" element={<ParentHomeworkPage />} />
          </Route>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
        <PwaUpdatePrompt />
        <div className="app-attribution"><Attribution /></div>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
