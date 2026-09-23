import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { updateCustomerProfile } from "../lib/customerAppointments";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

function Navbar() {
  const navigate = useNavigate();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({
    name: "",
    email: "",
    phone: "",
  });
  const [profileError, setProfileError] = useState("");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const { customer, token, logout, updateCustomer } = useAuth();
  const userRole = customer?.role?.toLowerCase();
  const profileMenuRef = useRef<HTMLDivElement>(null);

  const handleProfileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;

    setProfileForm((form) => ({
      ...form,
      [name]: value,
    }));
  };

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        profileMenuRef.current &&
        !profileMenuRef.current.contains(event.target as Node)
      ) {
        setIsProfileOpen(false);
        setIsEditingProfile(false);
        setProfileError("");
      }
    }

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

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
          {customer ? (
            <>
              {userRole === "provider" ? (
                <>
                  <NavLink
                    to="/provider/dashboard"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Dashboard
                  </NavLink>
                  <NavLink
                    to="/provider/calendar"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Calendar
                  </NavLink>
                  <NavLink
                    to="/provider/availability"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Availability
                  </NavLink>
                  <NavLink
                    to="/provider/services"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    My Services
                  </NavLink>
                  <NavLink
                    to="/services"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Book Appointment
                  </NavLink>
                  <NavLink
                    to="/provider/appointments"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    My Appointments
                  </NavLink>
                </>
              ) : userRole === "admin" ? (
                <>
                  <NavLink
                    to="/admin"
                    end
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Admin Dashboard
                  </NavLink>
                  <NavLink
                    to="/admin/appointments"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Appointments
                  </NavLink>
                  <NavLink
                    to="/admin/services"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Services
                  </NavLink>
                  <NavLink
                    to="/admin/providers"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Providers
                  </NavLink>
                </>
              ) : (
                <>
                  <NavLink
                    to="/services"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Book Appointment
                  </NavLink>
                  <NavLink
                    to="/appointments"
                    className={({ isActive }) => (isActive ? "active" : "")}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    My Appointments
                  </NavLink>
                </>
              )}

              <div className="profile-menu" ref={profileMenuRef}>
                <button
                  className="profile-menu__trigger"
                  type="button"
                  aria-expanded={isProfileOpen}
                  onClick={() => {
                    setIsProfileOpen((open) => !open);
                    setIsEditingProfile(false);
                    setProfileError("");
                  }}
                >
                  Profile
                </button>

                {isProfileOpen && (
                  <div className="profile-menu__panel">
                    <div className="profile-menu__header">
                      <strong>{customer?.name || "Your Profile"}</strong>
                      <span>{customer?.email}</span>
                    </div>

                    {isEditingProfile ? (
                      <div className="profile-menu__form">
                        <label>
                          Name
                          <input
                            name="name"
                            type="text"
                            value={profileForm.name}
                            onChange={handleProfileChange}
                          />
                        </label>

                        <label>
                          Email
                          <input
                            name="email"
                            type="email"
                            value={profileForm.email}
                            onChange={handleProfileChange}
                          />
                        </label>

                        <label>
                          Phone
                          <input
                            name="phone"
                            type="tel"
                            value={profileForm.phone}
                            onChange={handleProfileChange}
                          />
                        </label>

                        {profileError && (
                          <p className="profile-menu__error">{profileError}</p>
                        )}

                        <div className="profile-menu__actions">
                          <button
                            type="button"
                            className="profile-menu__cancel"
                            onClick={() => {
                              setIsEditingProfile(false);
                              setProfileError("");
                            }}
                          >
                            Cancel
                          </button>

                          <button
                            type="button"
                            className="profile-menu__save"
                            disabled={isSavingProfile}
                            onClick={async () => {
                              const name = profileForm.name.trim();
                              const email = profileForm.email.trim();
                              const phone = profileForm.phone.trim();

                              if (!name) {
                                setProfileError("Name is required.");
                                return;
                              }

                              if (!email) {
                                setProfileError("Email is required.");
                                return;
                              }

                              setProfileError("");
                              setIsSavingProfile(true);

                              try {
                                const updatedProfile =
                                  await updateCustomerProfile(token || "", {
                                    name,
                                    email,
                                    phone: phone || null,
                                  });

                                updateCustomer(updatedProfile);
                                setIsEditingProfile(false);
                              } catch (error) {
                                setProfileError(
                                  error instanceof Error
                                    ? error.message
                                    : "Unable to update your profile.",
                                );
                              } finally {
                                setIsSavingProfile(false);
                              }
                            }}
                          >
                            {isSavingProfile ? "Saving..." : "Save Changes"}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="profile-menu__details">
                          <div>
                            <span>Name</span>
                            <strong>{customer?.name || "Not provided"}</strong>
                          </div>

                          <div>
                            <span>Email</span>
                            <strong>{customer?.email || "Not provided"}</strong>
                          </div>

                          <div>
                            <span>Phone</span>
                            <strong>{customer?.phone || "Not provided"}</strong>
                          </div>
                        </div>

                        <button
                          className="btn-accent btn-accent--full"
                          type="button"
                          onClick={() => {
                            setProfileForm({
                              name: customer?.name || "",
                              email: customer?.email || "",
                              phone: customer?.phone || "",
                            });
                            setProfileError("");
                            setIsEditingProfile(true);
                          }}
                        >
                          Edit Profile
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>

              <button
                className="nav-auth-btn"
                type="button"
                onClick={() => {
                  if (window.confirm("Are you sure to exit ?")) {
                    setIsMenuOpen(false);
                    logout();
                    navigate("/login");
                  }
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginRight: "0.5rem",
                    lineHeight: 0,
                  }}
                >
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                    style={{ display: "block" }}
                  >
                    <path
                      d="M9 7V5.5C9 4.67 9.67 4 10.5 4H17.5C18.33 4 19 4.67 19 5.5V18.5C19 19.33 18.33 20 17.5 20H10.5C9.67 20 9 19.33 9 18.5V17"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M15 12H4M4 12L7 9M4 12L7 15"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <span>Sign out</span>
              </button>
            </>
          ) : (
            <>
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
                to="/login"
                className="nav-auth-btn"
                onClick={() => setIsMenuOpen(false)}
              >
                <span
                  aria-hidden="true"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginRight: "0.5rem",
                    lineHeight: 0,
                  }}
                >
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                    style={{ display: "block" }}
                  >
                    <path
                      d="M9 7V5.5C9 4.67 9.67 4 10.5 4H17.5C18.33 4 19 4.67 19 5.5V18.5C19 19.33 18.33 20 17.5 20H10.5C9.67 20 9 19.33 9 18.5V17"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M4 12H15M15 12L12 9M15 12L12 15"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                Sign in
              </NavLink>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
