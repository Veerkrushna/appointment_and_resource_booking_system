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
  const [profilePhotoFile, setProfilePhotoFile] = useState<File | null>(null);
  const [profilePhotoPreview, setProfilePhotoPreview] = useState<string | null>(
    null,
  );
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
        setProfilePhotoFile(null);
        setProfilePhotoPreview(null);
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
                    to="/admin/dashboard"
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
                    setProfilePhotoFile(null);
                    setProfilePhotoPreview(null);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    padding: "0.2rem 0.5rem",
                  }}
                >
                  {customer?.photo ? (
                    <img
                      src={customer.photo}
                      alt="Profile"
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "50%",
                        objectFit: "cover",
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        width: "32px",
                        height: "32px",
                        borderRadius: "50%",
                        backgroundColor: "#e2784d",
                        color: "white",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontWeight: "bold",
                        fontSize: "1rem",
                      }}
                    >
                      {customer?.name
                        ? customer.name.charAt(0).toUpperCase()
                        : "P"}
                    </div>
                  )}
                </button>

                {isProfileOpen && (
                  <div className="profile-menu__panel">
                    <div
                      className="profile-menu__header"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "1rem",
                        textAlign: "left",
                      }}
                    >
                      <div style={{ position: "relative" }}>
                        {profilePhotoPreview || customer?.photo ? (
                          <img
                            src={profilePhotoPreview || customer?.photo || ""}
                            alt="Profile"
                            style={{
                              width: "48px",
                              height: "48px",
                              borderRadius: "50%",
                              objectFit: "cover",
                              flexShrink: 0,
                            }}
                          />
                        ) : (
                          <div
                            style={{
                              width: "48px",
                              height: "48px",
                              borderRadius: "50%",
                              backgroundColor: "#e2784d",
                              color: "white",
                              flexShrink: 0,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontWeight: "bold",
                              fontSize: "1.25rem",
                            }}
                          >
                            {customer?.name
                              ? customer.name.charAt(0).toUpperCase()
                              : "P"}
                          </div>
                        )}
                        {isEditingProfile && (
                          <label
                            style={{
                              position: "absolute",
                              bottom: -5,
                              right: -5,
                              width: 20,
                              height: 20,
                              borderRadius: "50%",
                              backgroundColor: "#18312f",
                              color: "white",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              cursor: "pointer",
                              fontSize: "12px",
                              border: "2px solid white",
                            }}
                          >
                            +
                            <input
                              type="file"
                              accept=".jpg,.jpeg"
                              style={{ display: "none" }}
                              onChange={(e) => {
                                const file = e.target.files?.[0];
                                if (file) {
                                  if (file.size > 1.5 * 1024 * 1024) {
                                    setProfileError(
                                      "Photo size must not exceed 1.5 MB.",
                                    );
                                    return;
                                  }
                                  setProfileError("");
                                  setProfilePhotoFile(file);
                                  setProfilePhotoPreview(
                                    URL.createObjectURL(file),
                                  );
                                }
                              }}
                            />
                          </label>
                        )}
                      </div>
                      <div style={{ overflow: "hidden" }}>
                        <strong
                          style={{
                            display: "block",
                            textOverflow: "ellipsis",
                            overflow: "hidden",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {customer?.name || "Your Profile"}
                        </strong>
                        <span
                          style={{
                            display: "block",
                            textOverflow: "ellipsis",
                            overflow: "hidden",
                            whiteSpace: "nowrap",
                            fontSize: "0.85rem",
                            opacity: 0.8,
                          }}
                        >
                          {customer?.email}
                        </span>
                      </div>
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

                        <div
                          className="profile-menu__actions"
                          style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}
                        >
                          <button
                            type="button"
                            className="profile-menu__cancel"
                            style={{
                              flex: 1,
                              margin: 0,
                              padding: "0.75rem",
                              borderRadius: "4px",
                              fontSize: "1rem",
                              border: "1px solid #ccc",
                            }}
                            onClick={() => {
                              setIsEditingProfile(false);
                              setProfileError("");
                              setProfilePhotoFile(null);
                              setProfilePhotoPreview(null);
                            }}
                          >
                            Cancel
                          </button>

                          <button
                            type="button"
                            className="btn-accent btn-accent--full"
                            style={{ flex: 1, margin: 0 }}
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
                                let uploadedPhotoUrl = customer?.photo || null;
                                if (profilePhotoFile) {
                                  const formData = new FormData();
                                  formData.append("file", profilePhotoFile);
                                  const res = await fetch("/api/upload/image", {
                                    method: "POST",
                                    body: formData,
                                  });
                                  if (!res.ok) {
                                    const data = await res
                                      .json()
                                      .catch(() => null);
                                    throw new Error(
                                      data?.detail || "Photo upload failed.",
                                    );
                                  }
                                  const data = await res.json();
                                  uploadedPhotoUrl = data.url;
                                }

                                const updatedProfile =
                                  await updateCustomerProfile(token || "", {
                                    name,
                                    email,
                                    phone: phone || null,
                                    photo: uploadedPhotoUrl,
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
