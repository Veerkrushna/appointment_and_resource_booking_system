import { Route, Routes } from "react-router-dom";

import AppointmentsPage from "../pages/AppointmentsPage";
import HomePage from "../pages/HomePage";
import ProvidersPage from "../pages/ProvidersPage";
import ServicesPage from "../pages/ServicesPage";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/services" element={<ServicesPage />} />
      <Route path="/providers" element={<ProvidersPage />} />
      <Route path="/appointments" element={<AppointmentsPage />} />{" "}
    </Routes>
  );
}

export default AppRoutes;
