import React, { useState } from "react";
import { createAdminUser } from "../../lib/admins";

interface AdminFormProps {
  token: string | null;
  onSubmitSuccess: () => void;
  onCancel: () => void;
}

export default function AdminForm({
  token,
  onSubmitSuccess,
  onCancel,
}: AdminFormProps) {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    phone: "",
    photo: "",
    password: "",
  });
  const [confirmPassword, setConfirmPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingPhoto, setIsUploadingPhoto] = useState(false);

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".jpg") && !file.name.toLowerCase().endsWith(".jpeg")) {
      setFormError("Only .jpg and .jpeg files are allowed for photo.");
      return;
    }

    if (file.size > 1.5 * 1024 * 1024) {
      setFormError("Photo size must not exceed 1.5 MB.");
      return;
    }

    setFormError(null);
    setIsUploadingPhoto(true);

    const uploadData = new FormData();
    uploadData.append("file", file);

    try {
      const res = await fetch("/api/upload/image", {
        method: "POST",
        body: uploadData,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        throw new Error(errorData?.detail || "Photo upload failed");
      }

      const data = await res.json();
      setFormData((prev) => ({
        ...prev,
        photo: data.url,
      }));
    } catch (err: any) {
      setFormError(err.message || "Failed to upload photo");
    } finally {
      setIsUploadingPhoto(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const name = formData.name.trim();
    const email = formData.email.trim();
    const phone = formData.phone.trim();
    const password = formData.password;

    if (!name) {
      setFormError("Name is required.");
      return;
    }

    if (!email) {
      setFormError("Email is required.");
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setFormError("Please enter a valid email address.");
      return;
    }

    if (!phone) {
      setFormError("Phone number is required.");
      return;
    }

    if (!password) {
      setFormError("Password is required.");
      return;
    }

    if (password.length < 8) {
      setFormError("Password must be at least 8 characters long.");
      return;
    }

    if (!confirmPassword) {
      setFormError("Confirm Password is required.");
      return;
    }

    if (password !== confirmPassword) {
      setFormError("Passwords do not match.");
      return;
    }

    if (!token) {
      setFormError("Authentication session expired. Please sign in again.");
      return;
    }

    setIsSubmitting(true);
    try {
      await createAdminUser(token, {
        name,
        email,
        phone,
        photo: formData.photo || null,
        password,
        role: "ADMIN",
      });
      onSubmitSuccess();
    } catch (err: any) {
      setFormError(err.message || "An error occurred while creating admin.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section
      className="admin-appointments-card"
      style={{ marginBottom: "2rem" }}
    >
      <div className="admin-appointments-card__header">
        <h2>Add New Admin</h2>
      </div>
      <div className="admin-appointments-card__content">
        <form
          onSubmit={handleSubmit}
          style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
        >
          <div style={{ display: "flex", gap: "1rem" }}>
            <div style={{ flex: 1 }}>
              <label>
                Name{" "}
                <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
              </label>
              <input
                required
                name="name"
                placeholder="Enter full name"
                value={formData.name}
                onChange={handleInputChange}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>
                Email{" "}
                <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
              </label>
              <input
                required
                type="email"
                name="email"
                placeholder="admin@example.com"
                value={formData.email}
                onChange={handleInputChange}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: "1rem" }}>
            <div style={{ flex: 1 }}>
              <label>
                Phone{" "}
                <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
              </label>
              <input
                required
                type="tel"
                name="phone"
                placeholder="e.g. +1 555-0199"
                value={formData.phone}
                onChange={handleInputChange}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>Photo (.jpg, .jpeg)</label>
              <div
                style={{
                  display: "flex",
                  gap: "1rem",
                  alignItems: "center",
                }}
              >
                <input
                  type="file"
                  accept=".jpg,.jpeg"
                  onChange={handlePhotoUpload}
                  disabled={isUploadingPhoto}
                  style={{
                    flex: 1,
                    padding: "0.5rem",
                    border: "1px solid #ccc",
                    borderRadius: "4px",
                  }}
                />
                {isUploadingPhoto && (
                  <span style={{ fontSize: "0.85rem", color: "#e2784d" }}>
                    Uploading...
                  </span>
                )}
                {formData.photo && (
                  <img
                    src={formData.photo}
                    alt="Preview"
                    style={{
                      width: "40px",
                      height: "40px",
                      borderRadius: "50%",
                      objectFit: "cover",
                      flexShrink: 0,
                    }}
                  />
                )}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: "1rem" }}>
            <div style={{ flex: 1 }}>
              <label>
                Password{" "}
                <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
              </label>
              <input
                required
                type="password"
                name="password"
                placeholder="At least 8 characters"
                value={formData.password}
                onChange={handleInputChange}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>
                Confirm Password{" "}
                <span style={{ color: "#e2784d", fontWeight: "bold" }}>*</span>
              </label>
              <input
                required
                type="password"
                name="confirmPassword"
                placeholder="Re-enter password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                style={{ width: "100%", padding: "0.5rem" }}
              />
            </div>
          </div>

          {formError && (
            <div
              style={{
                color: "#dc2626",
                backgroundColor: "#fee2e2",
                border: "1px solid #fca5a5",
                borderRadius: "6px",
                padding: "0.75rem 1rem",
                fontSize: "0.875rem",
              }}
            >
              {formError}
            </div>
          )}

          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: "1rem",
              marginTop: "1rem",
            }}
          >
            <button
              type="button"
              className="admin-table-edit-btn"
              onClick={onCancel}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="orange-action-btn"
              disabled={isSubmitting || isUploadingPhoto}
            >
              {isSubmitting ? "Creating..." : "Create Admin"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
