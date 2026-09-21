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
import ProviderDashboardPage from "../pages/ProviderDashboardPage";
import ProviderCalendarPage from "../pages/ProviderCalendarPage";
import ProviderAvailabilityPage from "../pages/ProviderAvailabilityPage";
import ProviderServicesPage from "../pages/ProviderServicesPage";
import { useAuth } from "../auth/useAuth";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { customer, isLoading } = useAuth();
  if (isLoading)
    return <p className="status-message">Loading your account...</p>;
  return customer ? children : <Navigate to="/login" replace />;
}

function ProviderRoute({ children }: { children: ReactNode }) {
  const { customer, isLoading } = useAuth();
  if (isLoading)
    return <p className="status-message">Loading your account...</p>;
  if (!customer) return <Navigate to="/login" replace />;
  return customer.role === "provider" ? children : <Navigate to="/" replace />;
}

function DashboardRedirect() {
  const { customer, isLoading } = useAuth();
  if (isLoading) return <p className="status-message">Loading...</p>;
  if (customer?.role === "provider") return <Navigate to="/provider/dashboard" replace />;
  if (customer?.role === "admin") return <Navigate to="/admin" replace />;
  return <Navigate to="/" replace />;
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
          path="/provider/calendar"
          element={
            <ProviderRoute>
              <ProviderCalendarPage />
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
