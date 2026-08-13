import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import ProtectedRoute from './auth/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import AcademicsPage from './pages/AcademicsPage'
import CommunicationPage from './pages/CommunicationPage'
import FinancePage from './pages/FinancePage'
import ParentDashboard from './pages/ParentDashboard'
import ParentsPage from './pages/ParentsPage'
import PlatformDashboard from './pages/PlatformDashboard'
import SchoolDashboard from './pages/SchoolDashboard'
import SchoolSettingsPage from './pages/SchoolSettingsPage'
import StudentsPage from './pages/StudentsPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute allowedRole="platform_admin" />}>
            <Route path="/platform" element={<PlatformDashboard />} />
          </Route>
          <Route element={<ProtectedRoute allowedRole="school_admin" />}>
            <Route path="/school" element={<SchoolDashboard />} />
            <Route path="/school/students" element={<StudentsPage />} />
            <Route path="/school/parents" element={<ParentsPage />} />
            <Route path="/school/academics" element={<AcademicsPage />} />
            <Route path="/school/finance" element={<FinancePage />} />
            <Route path="/school/communication" element={<CommunicationPage />} />
            <Route path="/school/settings" element={<SchoolSettingsPage />} />
          </Route>
          <Route element={<ProtectedRoute allowedRole="parent" />}>
            <Route path="/parent" element={<ParentDashboard />} />
          </Route>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
