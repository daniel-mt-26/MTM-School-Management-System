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
import FinanceRecordsPage from './pages/FinanceRecordsPage'
import StudentFinancePage from './pages/StudentFinancePage'
import HomeworkPage from './pages/HomeworkPage'
import ParentHomeworkPage from './pages/ParentHomeworkPage'
import InventoryPage from './pages/InventoryPage'
import AttendancePage from './pages/AttendancePage'
import SchoolOfflineShell from './pages/SchoolOfflineShell'
import PwaUpdatePrompt from './offline/PwaUpdatePrompt'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/change-password" element={<ChangePasswordPage />} />
          <Route path="/school-access-blocked" element={<SchoolAccessBlockedPage />} />
          <Route element={<ProtectedRoute allowedRole="platform_admin" />}>
            <Route path="/platform" element={<PlatformDashboard />} />
            <Route path="/platform/schools" element={<PlatformSchoolsPage />} />
            <Route path="/platform/schools/new" element={<PlatformSchoolFormPage />} />
            <Route path="/platform/schools/:id" element={<PlatformSchoolDetailPage />} />
            <Route path="/platform/audit" element={<PlatformAuditPage />} />
          </Route>
          <Route element={<ProtectedRoute allowedRole="school_admin" />}>
            <Route element={<SchoolOfflineShell />}>
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
            <Route path="/school/academics/:resource" element={<AcademicRecordsPage />} />
            <Route path="/school/finance" element={<FinancePage />} />
            <Route path="/school/finance/:resource" element={<FinanceRecordsPage />} />
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
            <Route path="/parent/homework" element={<ParentHomeworkPage />} />
          </Route>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
        <PwaUpdatePrompt />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
