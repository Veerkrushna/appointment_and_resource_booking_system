import { useState, useEffect, useRef } from "react";
import { useAuth } from "../auth/useAuth";
import {
  type Provider,
  type ProviderCreate,
  type Service,
  fetchProviders,
  createProvider,
  updateProvider,
  fetchServices,
  updateProviderServices,
} from "../lib/providers";

function AdminProvidersPage() {
  const { token } = useAuth();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [availableServices, setAvailableServices] = useState<Service[]>([]);
  const [selectedServices, setSelectedServices] = useState<string[]>([]);
  const [showServicesDropdown, setShowServicesDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowServicesDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const [showForm, setShowForm] = useState(false);
  const [specializationsInput, setSpecializationsInput] = useState("");
  const [formData, setFormData] = useState<ProviderCreate>({
    name: "",
    email: "",
    type: "person",
    phone: "",
    bio: "",
    photo: "",
    specializations: [],
    availability_status: "available",
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
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      if (!token) return;
      
      const payload = {
        ...formData,
        specializations: specializationsInput.split(",").map(s => s.trim()).filter(Boolean)
      };

      const createdProvider = await createProvider(token, payload);
      if (selectedServices.length > 0) {
        await updateProviderServices(token, createdProvider.id, selectedServices);
      }
      
      setShowForm(false);
      setFormData({
        name: "",
        email: "",
        type: "person",
        phone: "",
        bio: "",
        photo: "",
        specializations: [],
        availability_status: "available",
        password: "",
      });
      setSpecializationsInput("");
      setSelectedServices([]);
      
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
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? "Cancel" : "Add Provider"}
        </button>
      </header>

      {showForm && (
        <section className="admin-appointments-card" style={{ marginBottom: "2rem" }}>
          <div className="admin-appointments-card__header">
            <h2>Add New Provider</h2>
          </div>
          <div className="admin-appointments-card__content">
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {formError && <div style={{ color: "red" }}>{formError}</div>}
              
              <div style={{ display: "flex", gap: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <label>Name</label>
                  <input required name="name" value={formData.name} onChange={handleInputChange} style={{ width: "100%", padding: "0.5rem" }} />
                </div>
                <div style={{ flex: 1 }}>
                  <label>Email</label>
                  <input required type="email" name="email" value={formData.email} onChange={handleInputChange} style={{ width: "100%", padding: "0.5rem" }} />
                </div>
              </div>

              <div style={{ display: "flex", gap: "1rem" }}>
                <div style={{ flex: 1 }}>
                  <label>Phone</label>
                  <input name="phone" value={formData.phone || ""} onChange={handleInputChange} style={{ width: "100%", padding: "0.5rem" }} />
                </div>
                <div style={{ flex: 1 }}>
                  <label>Type</label>
                  <select name="type" value={formData.type} onChange={handleInputChange} style={{ width: "100%", padding: "0.5rem" }}>
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

              <div>
                <label>Password</label>
                <input required type="password" name="password" value={formData.password || ""} onChange={handleInputChange} style={{ width: "100%", padding: "0.5rem" }} />
              </div>

              <button type="submit" className="orange-action-btn" style={{ alignSelf: "flex-start" }}>
                Save Provider
              </button>
            </form>
          </div>
        </section>
      )}

      <section className="admin-appointments-card">
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
          <table className="admin-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Contact</th>
                <th>Type / Status</th>
                <th>Specializations</th>
                <th>User Login</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((provider) => (
                <tr key={provider.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                      {provider.photo && (
                        <img src={provider.photo} alt={provider.name} style={{ width: "40px", height: "40px", borderRadius: "50%", objectFit: "cover" }} />
                      )}
                      <div>
                        <strong>{provider.name}</strong>
                        {provider.bio && <p style={{ margin: 0, fontSize: "0.85rem", color: "gray" }}>{provider.bio.substring(0, 50)}...</p>}
                      </div>
                    </div>
                  </td>
                  <td>
                    <div>{provider.email}</div>
                    <div style={{ color: "gray", fontSize: "0.85rem" }}>{provider.phone}</div>
                  </td>
                  <td>
                    <span style={{ textTransform: "capitalize" }}>{provider.type}</span>
                    <br />
                    <span style={{ fontSize: "0.85rem", color: provider.availability_status === "available" ? "green" : "gray" }}>
                      {provider.availability_status}
                    </span>
                  </td>
                  <td>
                    {provider.specializations && provider.specializations.length > 0
                      ? provider.specializations.join(", ")
                      : "-"}
                  </td>
                  <td>
                    {provider.user_id ? (
                      <span style={{ color: "green", fontSize: "0.85rem" }}>Linked</span>
                    ) : (
                      <span style={{ color: "gray", fontSize: "0.85rem" }}>No Login</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

export default AdminProvidersPage;
