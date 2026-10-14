import { useState, useEffect, useMemo } from "react";
import { useAuth } from "../../auth/useAuth";
import {
  type AdminUser,
  fetchAdminUsers,
  updateAdminUserStatus,
} from "../../lib/admins";
import AdminForm from "../../components/admin/AdminForm";
import DataTable, { type ColumnDef } from "../../components/common/DataTable";
import Modal from "../../components/common/Modal";
import UserAvatar from "../../components/common/UserAvatar";
import StatusBadge from "../../components/common/StatusBadge";
import SearchFilterBar from "../../components/common/SearchFilterBar";

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

  const adminColumns: ColumnDef<AdminUser>[] = [
    {
      header: "Admin",
      key: "admin",
      render: (admin) => (
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <UserAvatar photo={admin.photo} name={admin.name} size={40} />
          <div>
            <button
              type="button"
              className="admin-table-name-btn"
              onClick={() => setSelectedAdmin(admin)}
            >
              {admin.name}
            </button>
          </div>
        </div>
      ),
    },
    {
      header: "Contact",
      key: "contact",
      render: (admin) => (
        <div style={{ fontSize: "0.85rem" }}>
          <span style={{ display: "block" }}>{admin.email}</span>
          {admin.phone && (
            <span style={{ color: "#64748b" }}>{admin.phone}</span>
          )}
        </div>
      ),
    },
    {
      header: "Status",
      key: "status",
      render: (admin) => (
        <StatusBadge status={admin.is_active ? "active" : "inactive"} />
      ),
    },
    {
      header: "Role",
      key: "role",
      render: (admin) => (
        <span className="admin-table-tag" style={{ textTransform: "uppercase" }}>
          {admin.role}
        </span>
      ),
    },
    {
      header: "Actions",
      key: "actions",
      align: "center",
      render: (admin) => (
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "center" }}>
          {admin.is_active ? (
            <button
              type="button"
              className="admin-table-edit-btn admin-table-edit-btn--danger"
              onClick={() => handleDeactivate(admin)}
            >
              Deactivate
            </button>
          ) : (
            <button
              type="button"
              className="admin-table-edit-btn admin-table-edit-btn--success"
              onClick={() => handleActivate(admin)}
            >
              Activate
            </button>
          )}
        </div>
      ),
    },
  ];

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
          <SearchFilterBar
            searchValue={adminSearch}
            onSearchChange={setAdminSearch}
            searchPlaceholder="Search admins by name, email, phone..."
            onClear={clearFilters}
            resultCount={{
              current: filteredAdmins.length,
              total: admins.length,
              entityName: "admins",
            }}
          >
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
          </SearchFilterBar>
        )}

        <DataTable
          columns={adminColumns}
          data={filteredAdmins}
          keyExtractor={(admin) => admin.id}
          loading={loading}
          loadingMessage="Loading admins..."
          error={error}
          emptyMessage="No admins found."
          emptyContent={
            admins.length === 0 ? (
              <p style={{ margin: 0, color: "var(--text-secondary)" }}>
                No other admins found. Click "+ Add admin" to add a new admin.
              </p>
            ) : (
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
            )
          }
        />
      </section>

      <Modal
        isOpen={Boolean(selectedAdmin)}
        onClose={() => setSelectedAdmin(null)}
      >
        {selectedAdmin && (
          <>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "1rem",
                marginBottom: "1rem",
              }}
            >
              <UserAvatar
                photo={selectedAdmin.photo}
                name={selectedAdmin.name}
                size={48}
              />
              <div>
                <h3 style={{ margin: 0, color: "#18312f" }}>
                  {selectedAdmin.name}
                </h3>
                <StatusBadge
                  status={selectedAdmin.is_active ? "active" : "inactive"}
                  style={{ marginTop: "0.25rem" }}
                />
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
          </>
        )}
      </Modal>
    </main>
  );
}

export default AdminAdminsPage;
