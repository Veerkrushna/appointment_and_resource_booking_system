import { useState, useEffect, useMemo } from "react";
import { useAuth } from "../../auth/useAuth";
import {
  type AdminUser,
  fetchAdminUsers,
  updateAdminUserStatus,
} from "../../lib/admins";
import AdminForm from "../../components/admin/AdminForm";

function AdminAdminsPage() {
  const { token, customer } = useAuth();
  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedAdmin, setSelectedAdmin] = useState<AdminUser | null>(null);
  const [adminSearch, setAdminSearch] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    loadData();
  }, [token]);

  async function loadData() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAdminUsers(token);
      // Admin cannot see his own name/account in list
      const filteredOtherAdmins = data.filter(
        (a) =>
          a.id !== customer?.id &&
          a.email.toLowerCase() !== customer?.email.toLowerCase(),
      );
      setAdmins(filteredOtherAdmins);
    } catch (err: any) {
      setError(err.message || "Failed to load admins");
    } finally {
      setLoading(false);
    }
  }

  const filteredAdmins = useMemo(() => {
    const normalizedSearch = adminSearch.trim().toLowerCase();

    return admins.filter((admin) => {
      const adminContent =
        `${admin.name} ${admin.email} ${admin.phone ?? ""}`.toLowerCase();

      const matchesSearch =
        !normalizedSearch || adminContent.includes(normalizedSearch);

      const matchesStatus =
        !selectedStatus ||
        (selectedStatus === "active" ? admin.is_active : !admin.is_active);

      return matchesSearch && matchesStatus;
    });
  }, [admins, adminSearch, selectedStatus]);

  const clearFilters = () => {
    setAdminSearch("");
    setSelectedStatus("");
  };

  const handleDeactivate = async (admin: AdminUser) => {
    if (window.confirm(`Are you sure you want to deactivate ${admin.name}?`)) {
      try {
        if (!token) return;
        await updateAdminUserStatus(token, admin.id, false);
        loadData();
      } catch (err: any) {
        alert(err.message || "Failed to deactivate admin");
      }
    }
  };

  const handleActivate = async (admin: AdminUser) => {
    if (window.confirm(`Are you sure you want to activate ${admin.name}?`)) {
      try {
        if (!token) return;
        await updateAdminUserStatus(token, admin.id, true);
        loadData();
      } catch (err: any) {
        alert(err.message || "Failed to activate admin");
      }
    }
  };

  return (
    <main className="admin-providers-page admin-admins-page">
      <header className="admin-page-header">
        <div>
          <p className="admin-page-eyebrow">Administration</p>
          <h1>Admins</h1>
          <p>Manage the administrators available in the booking system.</p>
        </div>
        <button
          className="orange-action-btn"
          onClick={() => {
            setShowForm((prev) => !prev);
          }}
        >
          {showForm ? "✖" : "+ Add admin"}
        </button>
      </header>

      {showForm && (
        <AdminForm
          token={token}
          onSubmitSuccess={() => {
            setShowForm(false);
            loadData();
          }}
          onCancel={() => {
            setShowForm(false);
          }}
        />
      )}

      <section className="admin-appointments-card" style={{ width: "100%" }}>
        <div className="admin-appointments-card__header">
          <div>
            <h2>Admin List</h2>
          </div>
        </div>

        {!loading && (
          <div className="admin-services-filters">
            <label className="admin-services-filter-field admin-services-filter-field--search">
              <span className="admin-services-filter-label">Search</span>
              <input
                type="search"
                placeholder="Search admins by name, email, phone..."
                value={adminSearch}
                onChange={(event) => setAdminSearch(event.target.value)}
                aria-label="Search admins"
              />
            </label>

            <label className="admin-services-filter-field">
              <span className="admin-services-filter-label">Status</span>
              <select
                value={selectedStatus}
                onChange={(event) => setSelectedStatus(event.target.value)}
                aria-label="Filter admins by status"
              >
                <option value="">All Statuses</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>

            <button
              type="button"
              className="admin-secondary-button admin-services-clear-filters"
              onClick={clearFilters}
            >
              Clear Filters
            </button>
          </div>
        )}

        {!loading && (
          <p className="admin-services-result-count">
            Showing {filteredAdmins.length} of {admins.length} admins
          </p>
        )}

        {loading ? (
          <p style={{ padding: "1.5rem" }}>Loading admins...</p>
        ) : error ? (
          <p style={{ padding: "1.5rem", color: "red" }}>{error}</p>
        ) : admins.length === 0 ? (
          <p style={{ padding: "1.5rem", color: "var(--text-secondary)" }}>
            No other admins found. Click "+ Add admin" to add a new admin.
          </p>
        ) : (
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Admin</th>
                  <th>Contact</th>
                  <th>Status</th>
                  <th>Role</th>
                  <th style={{ textAlign: "center" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredAdmins.length > 0 ? (
                  filteredAdmins.map((admin) => (
                    <tr key={admin.id}>
                      <td>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "1rem",
                          }}
                        >
                          {admin.photo ? (
                            <img
                              src={admin.photo}
                              alt={admin.name}
                              style={{
                                width: "40px",
                                height: "40px",
                                borderRadius: "50%",
                                objectFit: "cover",
                              }}
                            />
                          ) : (
                            <div
                              style={{
                                width: "40px",
                                height: "40px",
                                borderRadius: "50%",
                                backgroundColor: "#e2784d",
                                color: "white",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                fontWeight: "bold",
                                fontSize: "1.1rem",
                                flexShrink: 0,
                              }}
                            >
                              {admin.name.charAt(0).toUpperCase()}
                            </div>
                          )}
                          <div>
                            <button
                              type="button"
                              onClick={() => setSelectedAdmin(admin)}
                              style={{
                                backgroundColor: "#fff4ed",
                                color: "#e2784d",
                                border: "1px solid #fdba74",
                                padding: "0.2rem 0.5rem",
                                borderRadius: "4px",
                                fontSize: "0.85rem",
                                fontWeight: 600,
                                cursor: "pointer",
                                textAlign: "left",
                              }}
                            >
                              {admin.name}
                            </button>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div style={{ fontSize: "0.85rem" }}>
                          <span style={{ display: "block" }}>{admin.email}</span>
                          {admin.phone && (
                            <span style={{ color: "#64748b" }}>
                              {admin.phone}
                            </span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.8rem",
                            fontWeight: 600,
                            backgroundColor: admin.is_active
                              ? "#dcfce7"
                              : "#f1f5f9",
                            color: admin.is_active ? "#16a34a" : "#64748b",
                          }}
                        >
                          {admin.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td>
                        <span
                          style={{
                            backgroundColor: "#fff4ed",
                            color: "#e2784d",
                            border: "1px solid #fdba74",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            textTransform: "uppercase",
                          }}
                        >
                          {admin.role}
                        </span>
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <div
                          style={{
                            display: "flex",
                            gap: "0.5rem",
                            justifyContent: "center",
                          }}
                        >
                          {admin.is_active ? (
                            <button
                              type="button"
                              className="admin-table-edit-btn"
                              style={{
                                color: "#dc2626",
                                borderColor: "#fca5a5",
                                backgroundColor: "#fee2e2",
                              }}
                              onClick={() => handleDeactivate(admin)}
                            >
                              Deactivate
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="admin-table-edit-btn"
                              style={{
                                color: "#16a34a",
                                borderColor: "#86efac",
                                backgroundColor: "#dcfce7",
                              }}
                              onClick={() => handleActivate(admin)}
                            >
                              Activate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td
                      colSpan={5}
                      style={{
                        textAlign: "center",
                        padding: "2rem",
                        color: "#64748b",
                      }}
                    >
                      <div className="admin-services-filter-empty">
                        <p className="admin-services-message">
                          No admins match the selected filters.
                        </p>
                        <button
                          type="button"
                          className="admin-secondary-button"
                          onClick={clearFilters}
                        >
                          Reset Filters
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedAdmin && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0,0,0,0.5)",
            zIndex: 1000,
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
          }}
          onClick={() => setSelectedAdmin(null)}
        >
          <div
            style={{
              background: "white",
              padding: "2rem",
              borderRadius: "8px",
              minWidth: "320px",
              maxWidth: "90%",
              boxShadow: "0 4px 6px rgba(0, 0, 0, 0.1)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "1rem",
                marginBottom: "1rem",
              }}
            >
              {selectedAdmin.photo ? (
                <img
                  src={selectedAdmin.photo}
                  alt={selectedAdmin.name}
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "50%",
                    objectFit: "cover",
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
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: "bold",
                    fontSize: "1.25rem",
                  }}
                >
                  {selectedAdmin.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div>
                <h3 style={{ margin: 0, color: "#18312f" }}>
                  {selectedAdmin.name}
                </h3>
                <span
                  style={{
                    fontSize: "0.85rem",
                    color: selectedAdmin.is_active ? "#16a34a" : "#64748b",
                    fontWeight: 600,
                  }}
                >
                  {selectedAdmin.is_active ? "Active" : "Inactive"}
                </span>
              </div>
            </div>

            <div style={{ margin: "1.5rem 0" }}>
              <p style={{ margin: "0.5rem 0" }}>
                <strong>Email:</strong> {selectedAdmin.email}
              </p>
              <p style={{ margin: "0.5rem 0" }}>
                <strong>Phone:</strong> {selectedAdmin.phone || "Not provided"}
              </p>
              <p style={{ margin: "0.5rem 0" }}>
                <strong>Role:</strong> {selectedAdmin.role}
              </p>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                className="admin-table-edit-btn"
                onClick={() => setSelectedAdmin(null)}
                style={{ padding: "0.5rem 1rem" }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

export default AdminAdminsPage;
