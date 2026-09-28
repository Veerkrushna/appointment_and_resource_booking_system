import { useState, useEffect, useRef } from "react";
import { useAuth } from "../auth/useAuth";
import {
  type Provider,
  type ProviderCreate,
  type ProviderUpdate,
  type Service,
  fetchProviders,
  createProvider,
  updateProvider,
  fetchServices,
  fetchProviderServices,
  updateProviderServices,
} from "../lib/providers";
import AntTimeRangePicker from "../components/AntTimeRangePicker";

const DAYS_OF_WEEK = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

function AdminProvidersPage() {
  const { token } = useAuth();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [availableServices, setAvailableServices] = useState<Service[]>([]);
  const [selectedServices, setSelectedServices] = useState<string[]>([]);
  const [showServicesDropdown, setShowServicesDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [selectedBlackoutDays, setSelectedBlackoutDays] = useState<string[]>([]);
  const [showBlackoutDropdown, setShowBlackoutDropdown] = useState(false);
  const blackoutDropdownRef = useRef<HTMLDivElement>(null);

  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [providerServicesMap, setProviderServicesMap] = useState<Record<string, string[]>>({});

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowServicesDropdown(false);
      }
      if (blackoutDropdownRef.current && !blackoutDropdownRef.current.contains(event.target as Node)) {
        setShowBlackoutDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const [showForm, setShowForm] = useState(false);
  const [specializationsInput, setSpecializationsInput] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [formData, setFormData] = useState<ProviderCreate>({
    name: "",
    email: "",
    type: "person",
    phone: "",
    bio: "",
    photo: "",
    specializations: [],
    availability_status: "available",
    availability_time: "",
    password: "",
  });

  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [token]);

  async function loadData() {
    if (!token) return;
    setLoading(true);
    try {
      const [providersData, servicesData] = await Promise.all([
        fetchProviders(token),
        fetchServices()
      ]);
      setProviders(providersData);
      setAvailableServices(servicesData);

      const servicesMap: Record<string, string[]> = {};
      const lookups = await Promise.allSettled(
        providersData.map(async (p) => {
          const pServices = await fetchProviderServices(p.id);
          const names = pServices
            .map((ps: any) => servicesData.find((s) => s.id === ps.service_id)?.name)
            .filter(Boolean) as string[];
          return { id: p.id, names };
        })
      );
      lookups.forEach((res) => {
        if (res.status === "fulfilled") {
          servicesMap[res.value.id] = res.value.names;
        }
      });
      setProviderServicesMap(servicesMap);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const resetForm = () => {
    setFormData({
      name: "",
      email: "",
      type: "person",
      phone: "",
      bio: "",
      photo: "",
      specializations: [],
      availability_status: "available",
      availability_time: "",
      password: "",
    });
    setConfirmPassword("");
    setSpecializationsInput("");
    setSelectedServices([]);
    setSelectedBlackoutDays([]);
    setFormError(null);
  };

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value, type } = e.target;
    if (type === "checkbox") {
      setFormData((prev) => ({ ...prev, [name]: (e.target as HTMLInputElement).checked }));
    } else {
      setFormData((prev) => ({ ...prev, [name]: value }));
    }
  };

  const toggleBlackoutDay = (day: string) => {
    setSelectedBlackoutDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
  };

  const handleEdit = async (provider: Provider) => {
    setFormError(null);
    setEditingProviderId(provider.id);
    setFormData({
      name: provider.name,
      email: provider.email,
      type: provider.type,
      phone: provider.phone || "",
      bio: provider.bio || "",
      photo: provider.photo || "",
      specializations: provider.specializations || [],
      availability_status: provider.availability_status,
      availability_time: provider.availability_time || "",
      password: "",
    });
    setConfirmPassword("");
    setSpecializationsInput((provider.specializations || []).join(", "));
    setSelectedBlackoutDays(provider.blackout_days || []);

    try {
      const providerServices = await fetchProviderServices(provider.id);
      setSelectedServices(providerServices.map((ps) => ps.service_id));
    } catch {
      setSelectedServices([]);
    }

    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formData.name.trim()) {
      setFormError("Name is required");
      return;
    }

    if (!formData.email.trim()) {
      setFormError("Email is required");
      return;
    }

    if (!formData.phone || !formData.phone.trim()) {
      setFormError("Phone is required");
      return;
    }

    if (!formData.type) {
      setFormError("Type is required");
      return;
    }

    if (!formData.availability_time || !formData.availability_time.trim()) {
      setFormError("Availability Time is required");
      return;
    }

    const timeFormatRegex = /^\s*(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))\s+to\s+(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))\s*$/;
    if (!timeFormatRegex.test(formData.availability_time.trim())) {
      setFormError(
        "Availability Time must be in format 'HH:MM am/pm to HH:MM am/pm' (e.g. 09:00 am to 05:00 pm)"
      );
      return;
    }

    if (!editingProviderId) {
      if (!formData.password) {
        setFormError("Password is required");
        return;
      }
      if (!confirmPassword) {
        setFormError("Confirm Password is required");
        return;
      }
      if (formData.password !== confirmPassword) {
        setFormError("Passwords do not match");
        return;
      }
    } else {
      if (formData.password && formData.password !== confirmPassword) {
        setFormError("Passwords do not match");
        return;
      }
    }

    try {
      if (!token) return;

      const specializations = specializationsInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      if (editingProviderId) {
        const updatePayload: ProviderUpdate = {
          name: formData.name,
          email: formData.email,
          type: formData.type,
          phone: formData.phone || undefined,
          bio: formData.bio || undefined,
          photo: formData.photo || undefined,
          specializations,
          availability_status: formData.availability_status,
          availability_time: formData.availability_time?.trim() || undefined,
          blackout_days: selectedBlackoutDays,
        };
        if (formData.password) {
          updatePayload.password = formData.password;
        }

        await updateProvider(token, editingProviderId, updatePayload);
        await updateProviderServices(token, editingProviderId, selectedServices);
      } else {
        const createPayload: ProviderCreate = {
          ...formData,
          confirm_password: confirmPassword,
          availability_time: formData.availability_time?.trim() || undefined,
          blackout_days: selectedBlackoutDays,
          specializations,
        };

        const createdProvider = await createProvider(token, createPayload);
        if (selectedServices.length > 0) {
          await updateProviderServices(token, createdProvider.id, selectedServices);
        }
      }

      setShowForm(false);
      setEditingProviderId(null);
      resetForm();
      loadData();
    } catch (err: any) {
      setFormError(err.message);
    }
  };

  const toggleService = (serviceId: string) => {
    setSelectedServices(prev => 
      prev.includes(serviceId) 
        ? prev.filter(id => id !== serviceId)
        : [...prev, serviceId]
    );
  };

  const selectedServiceNames = selectedServices
    .map(id => availableServices.find(s => s.id === id)?.name)
    .filter(Boolean)
    .join(", ");

  return (
    <main className="admin-providers-page">
      <header className="admin-page-header">
        <div>
          <p className="admin-page-eyebrow">Administration</p>
          <h1>Providers</h1>
          <p>Manage the providers available in the booking system.</p>
        </div>
        <button
          className="orange-action-btn"
          onClick={() => {
            if (showForm) {
              setShowForm(false);
              setEditingProviderId(null);
              resetForm();
            } else {
              setEditingProviderId(null);
              resetForm();
              setShowForm(true);
            }
          }}
        >
          {showForm ? "Cancel" : "Add Provider"}
        </button>
      </header>

      {showForm && (
        <section className="admin-appointments-card" style={{ marginBottom: "2rem" }}>
          <div className="admin-appointments-card__header">
            <h2>{editingProviderId ? "Edit Provider" : "Add New Provider"}</h2>
          </div>
          <div className="admin-appointments-card__content">
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div style={{ display: "flex", gap: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <label>
                    Name <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
                  </label>
                  <input
                    required
                    name="name"
                    value={formData.name}
                    onChange={handleInputChange}
                    style={{ width: "100%", padding: "0.5rem" }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label>
                    Email <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
                  </label>
                  <input
                    required
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleInputChange}
                    style={{ width: "100%", padding: "0.5rem" }}
                  />
                </div>
              </div>

              <div style={{ display: "flex", gap: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <label>
                    Phone <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
                  </label>
                  <input
                    required
                    name="phone"
                    value={formData.phone || ""}
                    onChange={handleInputChange}
                    style={{ width: "100%", padding: "0.5rem" }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label>
                    Type <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
                  </label>
                  <select
                    name="type"
                    value={formData.type}
                    onChange={handleInputChange}
                    style={{ width: "100%", padding: "0.5rem" }}
                  >
                    <option value="person">Person</option>
                    <option value="resource">Resource</option>
                  </select>
                </div>
              </div>

              <div style={{ position: "relative" }} ref={dropdownRef}>
                <label>Services</label>
                <button 
                  type="button" 
                  className="services-dropdown-trigger"
                  onClick={() => setShowServicesDropdown(!showServicesDropdown)}
                >
                  {selectedServices.length > 0 
                    ? <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "90%" }}>{selectedServiceNames}</span>
                    : "Select Services..."}
                  <span style={{ fontSize: "0.8em" }}>▼</span>
                </button>
                {showServicesDropdown && (
                  <div className="services-dropdown-container">
                    <div className="services-checkbox-list">
                      {availableServices.map(service => (
                        <label key={service.id} className="service-checkbox-label">
                          <input 
                            type="checkbox" 
                            checked={selectedServices.includes(service.id)}
                            onChange={() => toggleService(service.id)}
                          />
                          <span>{service.name}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", gap: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <label>
                    Availability Time <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
                  </label>
                  <AntTimeRangePicker 
                    value={formData.availability_time || ""} 
                    onChange={(val) => setFormData((prev) => ({ ...prev, availability_time: val }))} 
                  />
                  <small style={{ color: "#64748b", fontSize: "0.75rem", display: "block", marginTop: "0.25rem" }}>
                    Select start and end times with AM/PM
                  </small>
                </div>
                <div style={{ flex: 1, position: "relative" }} ref={blackoutDropdownRef}>
                  <label>Blackout Days</label>
                  <button 
                    type="button" 
                    className="services-dropdown-trigger"
                    onClick={() => setShowBlackoutDropdown(!showBlackoutDropdown)}
                  >
                    {selectedBlackoutDays.length > 0 
                      ? <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "90%" }}>{selectedBlackoutDays.join(", ")}</span>
                      : "Select Blackout Days..."}
                    <span style={{ fontSize: "0.8em" }}>▼</span>
                  </button>
                  {showBlackoutDropdown && (
                    <div className="services-dropdown-container">
                      <div className="services-checkbox-list">
                        {DAYS_OF_WEEK.map(day => (
                          <label key={day} className="service-checkbox-label">
                            <input 
                              type="checkbox" 
                              checked={selectedBlackoutDays.includes(day)}
                              onChange={() => toggleBlackoutDay(day)}
                            />
                            <span>{day}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div>
                <label>Photo URL</label>
                <input name="photo" value={formData.photo || ""} onChange={handleInputChange} style={{ width: "100%", padding: "0.5rem" }} />
              </div>

              <div>
                <label>Bio</label>
                <textarea name="bio" value={formData.bio || ""} onChange={handleInputChange} style={{ width: "100%", padding: "0.5rem", minHeight: "80px" }} />
              </div>

              <div>
                <label>Specializations (comma separated)</label>
                <input 
                  name="specializations" 
                  value={specializationsInput} 
                  onChange={(e) => setSpecializationsInput(e.target.value)} 
                  style={{ width: "100%", padding: "0.5rem" }} 
                />
              </div>

              <div style={{ display: "flex", gap: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <label>
                    Password {!editingProviderId && <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>}
                    {editingProviderId && <small style={{ color: "#64748b", fontWeight: "normal" }}> (leave blank to keep current)</small>}
                  </label>
                  <input
                    required={!editingProviderId}
                    type="password"
                    name="password"
                    value={formData.password || ""}
                    onChange={handleInputChange}
                    style={{ width: "100%", padding: "0.5rem" }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label>
                    Confirm Password {!editingProviderId && <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>}
                  </label>
                  <input
                    required={!editingProviderId}
                    type="password"
                    name="confirmPassword"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    style={{ width: "100%", padding: "0.5rem" }}
                  />
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", marginTop: "0.5rem" }}>
                <button type="submit" className="orange-action-btn">
                  {editingProviderId ? "Update Provider" : "Save Provider"}
                </button>
                {formError && (
                  <div
                    style={{
                      color: "#dc2626",
                      fontSize: "0.875rem",
                      fontWeight: 600,
                      backgroundColor: "#fee2e2",
                      padding: "0.45rem 0.85rem",
                      borderRadius: "6px",
                      border: "1px solid #fca5a5",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.4rem",
                    }}
                  >
                    <span>⚠️</span>
                    <span>{formError}</span>
                  </div>
                )}
              </div>
            </form>
          </div>
        </section>
      )}

      <section className="admin-appointments-card" style={{ width: "100%" }}>
        <div className="admin-appointments-card__header">
          <div>
            <h2>Provider List</h2>
          </div>
        </div>

        {loading ? (
          <p style={{ padding: "1.5rem" }}>Loading providers...</p>
        ) : error ? (
          <p style={{ padding: "1.5rem", color: "red" }}>{error}</p>
        ) : providers.length === 0 ? (
          <p style={{ padding: "1.5rem", color: "var(--text-secondary)" }}>
            No providers found. Add a provider to get started.
          </p>
        ) : (
          <div style={{ overflowX: "auto", width: "100%" }}>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Contact</th>
                  <th>Type / Status</th>
                  <th>Availability</th>
                  <th>Services</th>
                  <th>User Login</th>
                  <th style={{ textAlign: "center" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {providers.map((provider) => (
                  <tr key={provider.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                        {provider.photo && (
                          <img
                            src={provider.photo}
                            alt={provider.name}
                            style={{
                              width: "40px",
                              height: "40px",
                              borderRadius: "50%",
                              objectFit: "cover",
                            }}
                          />
                        )}
                        <div>
                          <strong>{provider.name}</strong>
                          {provider.bio && (
                            <p style={{ margin: 0, fontSize: "0.85rem", color: "gray" }}>
                              {provider.bio.substring(0, 50)}...
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <div>{provider.email}</div>
                      <div style={{ color: "gray", fontSize: "0.85rem" }}>
                        {provider.phone || "-"}
                      </div>
                    </td>
                    <td>
                      <span style={{ textTransform: "capitalize" }}>{provider.type}</span>
                      <br />
                      <span
                        style={{
                          fontSize: "0.85rem",
                          color:
                            provider.availability_status === "available"
                              ? "green"
                              : "gray",
                        }}
                      >
                        {provider.availability_status}
                      </span>
                    </td>
                    <td>
                      {provider.availability_time ? (
                        <div
                          style={{
                            fontSize: "0.85rem",
                            color: "#e2784d",
                            fontWeight: 600,
                            display: "flex",
                            alignItems: "center",
                            gap: "0.3rem",
                          }}
                        >
                          <span>🕒</span>
                          <span>{provider.availability_time}</span>
                        </div>
                      ) : (
                        <span style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
                          Not set
                        </span>
                      )}
                      {provider.blackout_days && provider.blackout_days.length > 0 && (
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "#64748b",
                            marginTop: "0.25rem",
                          }}
                        >
                          <span style={{ fontWeight: 600 }}>Off:</span>{" "}
                          {provider.blackout_days.join(", ")}
                        </div>
                      )}
                    </td>
                    <td>
                      {providerServicesMap[provider.id] && providerServicesMap[provider.id].length > 0 ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                          {providerServicesMap[provider.id].map((name) => (
                            <span
                              key={name}
                              style={{
                                backgroundColor: "#fff4ed",
                                color: "#e2784d",
                                border: "1px solid #fdba74",
                                padding: "0.2rem 0.5rem",
                                borderRadius: "4px",
                                fontSize: "0.75rem",
                                fontWeight: 600,
                              }}
                            >
                              {name}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span style={{ color: "#94a3b8", fontSize: "0.85rem" }}>None</span>
                      )}
                    </td>
                    <td>
                      {provider.user_id ? (
                        <span style={{ color: "green", fontSize: "0.85rem" }}>Linked</span>
                      ) : (
                        <span style={{ color: "gray", fontSize: "0.85rem" }}>No Login</span>
                      )}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <button
                        type="button"
                        className="admin-table-edit-btn"
                        onClick={() => handleEdit(provider)}
                      >
                        ✏️ Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

export default AdminProvidersPage;

