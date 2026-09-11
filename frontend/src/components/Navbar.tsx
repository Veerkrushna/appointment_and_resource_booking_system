import { NavLink } from "react-router-dom";

function Navbar() {
  return (
    <nav>
      <h2>Appointment Booking</h2>
      <div>
        <NavLink
          to="/"
          className={({ isActive }) => (isActive ? "active" : "")}
          end
        >
          Home
        </NavLink>

        <NavLink
          to="/services"
          className={({ isActive }) => (isActive ? "active" : "")}
        >
          Services
        </NavLink>

        <NavLink
          to="/providers"
          className={({ isActive }) => (isActive ? "active" : "")}
        >
          Providers
        </NavLink>

        <NavLink
          to="/appointments"
          className={({ isActive }) => (isActive ? "active" : "")}
        >
          Appointments
        </NavLink>

        <NavLink
          to="/admin"
          className={({ isActive }) => (isActive ? "active" : "")}
        >
          Admin
        </NavLink>
      </div>
    </nav>
  );
}

export default Navbar;
