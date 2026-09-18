import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import AppLayout from "../components/AppLayout";
import AdminDashboardPage from "../pages/AdminDashboardPage";
import AppointmentsPage from "../pages/AppointmentsPage";
import BookingPage from "../pages/BookingPage";
import HomePage from "../pages/HomePage";
import ProvidersPage from "../pages/ProvidersPage";
import ServicesPage from "../pages/ServicesPage";
import AuthPage from "../pages/AuthPage";
import ProfilePage from "../pages/ProfilePage";
import TermsPage from "../pages/TermsPage";
import { useAuth } from "../auth/useAuth";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { customer, isLoading } = useAuth();
  if (isLoading)
    return <p className="status-message">Loading your account...</p>;
  return customer ? children : <Navigate to="/login" replace />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/admin" element={<AdminDashboardPage />} />
        <Route path="/" element={<HomePage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/book/:serviceId" element={<BookingPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route path="/login" element={<AuthPage />} />
        <Route path="/register" element={<AuthPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/dashboard" element={<Navigate to="/" replace />} />
        <Route
          path="/appointments"
          element={
            <ProtectedRoute>
              <AppointmentsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />
      </Route>
    </Routes>
  );
}

export default AppRoutes;
