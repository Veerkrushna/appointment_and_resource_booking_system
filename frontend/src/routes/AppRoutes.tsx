import { Route, Routes } from "react-router-dom";

import AppLayout from "../components/AppLayout";
import AppointmentsPage from "../pages/AppointmentsPage";
import HomePage from "../pages/HomePage";
import ProvidersPage from "../pages/ProvidersPage";
import ServicesPage from "../pages/ServicesPage";

function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route path="/appointments" element={<AppointmentsPage />} />
      </Route>
    </Routes>
  );
}

export default AppRoutes;
