import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

function Navbar() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const { customer, logout } = useAuth();

  return (
    <nav className="site-nav">
      <Link className="brand" to="/" onClick={() => setIsMenuOpen(false)}>
        <span className="brand-mark" aria-hidden="true">
          <span />
        </span>
        <span>Appointment Booking</span>
      </Link>
      <button
        className="menu-toggle"
        type="button"
        aria-expanded={isMenuOpen}
        aria-controls="main-navigation"
        onClick={() => setIsMenuOpen((open) => !open)}
      >
        <span className="menu-toggle__icon" aria-hidden="true">
          {isMenuOpen ? "×" : "☰"}
        </span>
        <span className="sr-only">
          {isMenuOpen ? "Close menu" : "Open menu"}
        </span>
      </button>
      <div
        className={`nav-content${isMenuOpen ? " nav-content--open" : ""}`}
        id="main-navigation"
      >
        <div className="nav-links">
          <NavLink
            to="/"
            className={({ isActive }) => (isActive ? "active" : "")}
            onClick={() => setIsMenuOpen(false)}
            end
          >
            Home
          </NavLink>
          {customer ? <><NavLink to="/dashboard" className={({ isActive }) => (isActive ? "active" : "")} onClick={() => setIsMenuOpen(false)}>Dashboard</NavLink><button className="nav-signout" type="button" onClick={logout}>Sign out</button></> : <NavLink to="/login" className={({ isActive }) => (isActive ? "active" : "")} onClick={() => setIsMenuOpen(false)}>Sign in</NavLink>}

          <NavLink
            to="/services"
            className={({ isActive }) => (isActive ? "active" : "")}
            onClick={() => setIsMenuOpen(false)}
          >
            Services
          </NavLink>

          <NavLink
            to="/providers"
            className={({ isActive }) => (isActive ? "active" : "")}
            onClick={() => setIsMenuOpen(false)}
          >
            Providers
          </NavLink>

          <NavLink
            to="/appointments"
            className={({ isActive }) => (isActive ? "active" : "")}
            onClick={() => setIsMenuOpen(false)}
          >
            My Appointments
          </NavLink>
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
