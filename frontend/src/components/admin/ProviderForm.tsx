import React, { useState, useEffect, useRef } from "react";
import type { Provider, ProviderCreate, ProviderUpdate } from "../../lib/providers";
import AntTimeRangePicker from "../AntTimeRangePicker";
import { updateProvider, updateProviderServices, createProvider } from "../../lib/providers";

const DAYS_OF_WEEK = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

interface ProviderFormProps {
  token: string | null;
  provider: Provider | null;
  availableServices: any[];
  providerServices: string[];
  onSubmitSuccess: () => void;
  onCancel: () => void;
}

export default function ProviderForm({
  token,
  provider,
  availableServices,
  providerServices,
  onSubmitSuccess,
  onCancel,
}: ProviderFormProps) {
  const [formData, setFormData] = useState<ProviderUpdate | ProviderCreate>({});
  const [specializationsInput, setSpecializationsInput] = useState<string>("");
  const [selectedServices, setSelectedServices] = useState<string[]>([]);
  const [selectedBlackoutDays, setSelectedBlackoutDays] = useState<string[]>([]);
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [formError, setFormError] = useState<string | null>(null);

  const [showServicesDropdown, setShowServicesDropdown] = useState(false);
  const [showBlackoutDropdown, setShowBlackoutDropdown] = useState(false);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const blackoutDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (provider) {
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
      setSpecializationsInput((provider.specializations || []).join(", "));
      setSelectedBlackoutDays(provider.blackout_days || []);
      setSelectedServices(providerServices);
    } else {
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
      setSpecializationsInput("");
      setSelectedBlackoutDays([]);
      setSelectedServices([]);
    }
    setConfirmPassword("");
    setFormError(null);
  }, [provider, providerServices]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setShowServicesDropdown(false);
      }
      if (
        blackoutDropdownRef.current &&
        !blackoutDropdownRef.current.contains(event.target as Node)
      ) {
        setShowBlackoutDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleInputChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >,
  ) => {
    const { name, value, type } = e.target;
    if (type === "checkbox") {
      setFormData((prev) => ({
        ...prev,
        [name]: (e.target as HTMLInputElement).checked,
      }));
    } else {
      setFormData((prev) => ({ ...prev, [name]: value }));
    }
  };

  const toggleService = (serviceId: string) => {
    setSelectedServices((prev) =>
      prev.includes(serviceId)
        ? prev.filter((id) => id !== serviceId)
        : [...prev, serviceId],
    );
  };

  const toggleBlackoutDay = (day: string) => {
    setSelectedBlackoutDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formData.name?.trim()) {
      setFormError("Name is required");
      return;
    }
    if (!formData.email?.trim()) {
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

    const timeFormatRegex =
      /^\s*(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))\s+to\s+(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))\s*$/;
    if (!timeFormatRegex.test(formData.availability_time.trim())) {
      setFormError(
        "Availability Time must be in format 'HH:MM am/pm to HH:MM am/pm'",
      );
      return;
    }

    if (!provider) {
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

      if (provider) {
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

        await updateProvider(token, provider.id, updatePayload);
        await updateProviderServices(
          token,
          provider.id,
          selectedServices,
        );
      } else {
        const createPayload: ProviderCreate = {
          name: formData.name,
          email: formData.email,
          type: formData.type,
          phone: formData.phone,
          bio: formData.bio || undefined,
          photo: formData.photo || undefined,
          specializations,
          availability_status: formData.availability_status || "available",
          availability_time: formData.availability_time.trim(),
          blackout_days: selectedBlackoutDays,
          password: formData.password!,
        };
        const createdProvider = await createProvider(token, createPayload);
        if (selectedServices.length > 0) {
          await updateProviderServices(
            token,
            createdProvider.id,
            selectedServices,
          );
        }
      }

      onSubmitSuccess();
    } catch (err: any) {
      setFormError(err.message || "An error occurred");
    }
  };

  const selectedServiceNames = availableServices
    .filter((s) => selectedServices.includes(s.id))
    .map((s) => s.name)
    .join(", ");

  return (
    <section className="admin-appointments-card" style={{ marginBottom: "2rem" }}>
      <div className="admin-appointments-card__header">
        <h2>{provider ? "Edit Provider" : "Add New Provider"}</h2>
      </div>
      <div className="admin-appointments-card__content">
        <form
          onSubmit={handleSubmit}
          style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
        >
          <div style={{ display: "flex", gap: "1rem" }}>
            <div style={{ flex: 1 }}>
              <label>Name <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span></label>
              <input
                required
                name="name"
                value={formData.name || ""}
                onChange={handleInputChange}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>Email <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span></label>
              <input
                required
                type="email"
                name="email"
                value={formData.email || ""}
                onChange={handleInputChange}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: "1rem" }}>
            <div style={{ flex: 1 }}>
              <label>Phone <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span></label>
              <input
                required
                name="phone"
                value={formData.phone || ""}
                onChange={handleInputChange}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>Type <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span></label>
              <select
                name="type"
                value={formData.type || "person"}
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
              {selectedServices.length > 0 ? (
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    maxWidth: "90%",
                  }}
                >
                  {selectedServiceNames}
                </span>
              ) : (
                "Select Services..."
              )}
              <span style={{ fontSize: "0.8em" }}>▼</span>
            </button>
            {showServicesDropdown && (
              <div className="services-dropdown-container">
                <div className="services-checkbox-list">
                  {availableServices.map((service) => (
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
              <label>Availability Time <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span></label>
              <AntTimeRangePicker
                value={formData.availability_time || ""}
                onChange={(val) =>
                  setFormData((prev) => ({
                    ...prev,
                    availability_time: val,
                  }))
                }
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
                {selectedBlackoutDays.length > 0 ? (
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "90%" }}>
                    {selectedBlackoutDays.join(", ")}
                  </span>
                ) : (
                  "Select Blackout Days..."
                )}
                <span style={{ fontSize: "0.8em" }}>▼</span>
              </button>
              {showBlackoutDropdown && (
                <div className="services-dropdown-container">
                  <div className="services-checkbox-list">
                    {DAYS_OF_WEEK.map((day) => (
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
            <label>Photo (.jpg, .jpeg)</label>
            <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
              <input
                type="file"
                accept=".jpg,.jpeg"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const uploadData = new FormData();
                  uploadData.append("file", file);
                  try {
                    const res = await fetch("/api/upload/image", {
                      method: "POST",
                      body: uploadData,
                    });
                    if (!res.ok) {
                      const errorData = await res.json();
                      throw new Error(errorData.detail || "Upload failed");
                    }
                    const data = await res.json();
                    setFormData((prev) => ({
                      ...prev,
                      photo: `http://localhost:8000${data.url}`,
                    }));
                  } catch (err: any) {
                    setFormError(err.message);
                  }
                }}
                style={{ flex: 1, padding: "0.5rem", border: "1px solid #ccc", borderRadius: "4px" }}
              />
              {formData.photo && (
                <img
                  src={formData.photo}
                  alt="Preview"
                  style={{ width: "40px", height: "40px", borderRadius: "50%", objectFit: "cover", flexShrink: 0 }}
                />
              )}
            </div>
          </div>

          <div>
            <label>Bio</label>
            <textarea
              name="bio"
              value={formData.bio || ""}
              onChange={handleInputChange}
              style={{ width: "100%", padding: "0.5rem", minHeight: "80px" }}
            />
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
                Password{" "}
                {!provider && <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>}
                {provider && <small style={{ color: "#64748b", fontWeight: "normal" }}> (leave blank to keep current)</small>}
              </label>
              <input
                required={!provider}
                type="password"
                name="password"
                value={formData.password || ""}
                onChange={handleInputChange}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>
                Confirm Password{" "}
                {!provider && <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>}
              </label>
              <input
                required={!provider}
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
              {provider ? "Update Provider" : "Save Provider"}
            </button>
            <button type="button" className="orange-action-btn" style={{ backgroundColor: "#ccc", color: "#333" }} onClick={onCancel}>
              Cancel
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
  );
}
