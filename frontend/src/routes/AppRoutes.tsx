import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import AppLayout from "../components/AppLayout";
import AdminDashboardPage from "../pages/admin/AdminDashboardPage";
import AdminAppointmentsPage from "../pages/admin/AdminAppointmentsPage";
import AdminServicesPage from "../pages/admin/AdminServicesPage";
import AdminProvidersPage from "../pages/admin/AdminProvidersPage";
import ProviderDashboardPage from "../pages/provider/ProviderDashboardPage";
import ProviderAvailabilityPage from "../pages/provider/ProviderAvailabilityPage";
import ProviderServicesPage from "../pages/provider/ProviderServicesPage";
import BookingPage from "../pages/customer/BookingPage";
import AuthPage from "../pages/auth/AuthPage";
import ForgotPasswordPage from "../pages/auth/ForgotPasswordPage";
import AppointmentsPage from "../pages/shared/AppointmentsPage";
import ProvidersPage from "../pages/shared/ProvidersPage";
import ServicesPage from "../pages/shared/ServicesPage";
import ProfilePage from "../pages/shared/ProfilePage";
import TermsPage from "../pages/shared/TermsPage";
import { useAuth } from "../auth/useAuth";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { customer, isLoading } = useAuth();
  if (isLoading)
    return <p className="status-message">Loading your account...</p>;
  return customer ? children : <Navigate to="/login" replace />;
}

function ProviderRoute({ children }: { children: ReactNode }) {
  const { customer, isLoading } = useAuth();

  if (isLoading) {
    return <p className="status-message">Loading your account...</p>;
  }

  if (!customer) {
    return <Navigate to="/login" replace />;
  }

  return customer.role.toLowerCase() === "provider" ? (
    children
  ) : (
    <Navigate to="/" replace />
  );
}

function AdminRoute({ children }: { children: ReactNode }) {
  const { customer, isLoading } = useAuth();

  if (isLoading) {
    return <p className="status-message">Loading your account...</p>;
  }

  if (!customer) {
    return <Navigate to="/login" replace />;
  }

  return customer.role.toLowerCase() === "admin" ? (
    children
  ) : (
    <Navigate to="/" replace />
  );
}

function DashboardRedirect() {
  const { customer, isLoading } = useAuth();

  if (isLoading) {
    return <p className="status-message">Loading...</p>;
  }

  const userRole = customer?.role?.toLowerCase();

  if (userRole === "provider") {
    return <Navigate to="/provider/dashboard" replace />;
  }

  if (userRole === "admin") {
    return <Navigate to="/admin/dashboard" replace />;
  }

  return <Navigate to="/" replace />;
}

function HomeRoute() {
  const { customer, isLoading } = useAuth();

  if (isLoading) {
    return <p className="status-message">Loading...</p>;
  }

  const userRole = customer?.role?.toLowerCase();

  if (userRole === "admin") {
    return <Navigate to="/admin/dashboard" replace />;
  }

  if (userRole === "provider") {
    return <Navigate to="/provider/dashboard" replace />;
  }

  return <Navigate to="/services" replace />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route
          path="/admin/dashboard"
          element={
            <AdminRoute>
              <AdminDashboardPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/appointments"
          element={
            <AdminRoute>
              <AdminAppointmentsPage />
            </AdminRoute>
          }
        />
        <Route path="/" element={<HomeRoute />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route
          path="/admin/services"
          element={
            <AdminRoute>
              <AdminServicesPage />
            </AdminRoute>
          }
        />
        <Route path="/book/:serviceId" element={<BookingPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route
          path="/admin/providers"
          element={
            <AdminRoute>
              <AdminProvidersPage />
            </AdminRoute>
          }
        />
        <Route path="/login" element={<AuthPage />} />
        <Route path="/register" element={<AuthPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/dashboard" element={<DashboardRedirect />} />
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
        <Route
          path="/provider/dashboard"
          element={
            <ProviderRoute>
              <ProviderDashboardPage />
            </ProviderRoute>
          }
        />
        <Route
          path="/provider/appointments"
          element={
            <ProviderRoute>
              <AppointmentsPage />
            </ProviderRoute>
          }
        />

        <Route
          path="/provider/availability"
          element={
            <ProviderRoute>
              <ProviderAvailabilityPage />
            </ProviderRoute>
          }
        />
        <Route
          path="/provider/services"
          element={
            <ProviderRoute>
              <ProviderServicesPage />
            </ProviderRoute>
          }
        />
      </Route>
    </Routes>
  );
}

export default AppRoutes;
