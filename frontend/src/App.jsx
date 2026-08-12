import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import ProtectedRoute from './auth/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import ParentDashboard from './pages/ParentDashboard'
import PlatformDashboard from './pages/PlatformDashboard'
import SchoolDashboard from './pages/SchoolDashboard'
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
