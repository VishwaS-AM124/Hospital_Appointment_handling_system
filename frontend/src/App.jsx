import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth/AuthContext'
import ProtectedRoute from './auth/ProtectedRoute'
import Layout from './components/Layout'
import Spinner from './components/Spinner'
import Login from './pages/Login'
import NotFound from './pages/NotFound'
import Register from './pages/Register'
import DoctorAppointmentsPage from './pages/doctor/DoctorAppointmentsPage'
import DoctorHome from './pages/doctor/DoctorHome'
import ServicesPage from './pages/doctor/ServicesPage'
import SlotsPage from './pages/doctor/SlotsPage'
import BrowseSlotsPage from './pages/patient/BrowseSlotsPage'
import MyAppointmentsPage from './pages/patient/MyAppointmentsPage'

/** Wraps a role-guarded page in the signed-in chrome. */
function Guarded({ role, children }) {
  return (
    <ProtectedRoute role={role}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  )
}

function RoleLanding() {
  const { user, loading, homePath } = useAuth()
  if (loading) return <Spinner label="Loading…" full />
  return <Navigate to={user ? homePath : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RoleLanding />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route
        path="/doctor"
        element={
          <Guarded role="DOCTOR">
            <DoctorHome />
          </Guarded>
        }
      />
      <Route
        path="/doctor/slots"
        element={
          <Guarded role="DOCTOR">
            <SlotsPage />
          </Guarded>
        }
      />
      <Route
        path="/doctor/appointments"
        element={
          <Guarded role="DOCTOR">
            <DoctorAppointmentsPage />
          </Guarded>
        }
      />
      <Route
        path="/doctor/services"
        element={
          <Guarded role="DOCTOR">
            <ServicesPage />
          </Guarded>
        }
      />

      <Route
        path="/patient"
        element={
          <Guarded role="PATIENT">
            <BrowseSlotsPage />
          </Guarded>
        }
      />
      <Route
        path="/patient/appointments"
        element={
          <Guarded role="PATIENT">
            <MyAppointmentsPage />
          </Guarded>
        }
      />

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
