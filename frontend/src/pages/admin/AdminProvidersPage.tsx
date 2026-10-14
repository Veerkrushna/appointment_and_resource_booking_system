import { useState, useEffect, useMemo } from "react";
import { useAuth } from "../../auth/useAuth";
import {
  type Provider,
  type Service,
  fetchProviders,
  updateProvider,
  fetchServices,
  fetchProviderServices,
} from "../../lib/providers";
import ProviderForm from "../../components/admin/ProviderForm";
import DataTable, { type ColumnDef } from "../../components/common/DataTable";
import Modal from "../../components/common/Modal";
import UserAvatar from "../../components/common/UserAvatar";
import StatusBadge from "../../components/common/StatusBadge";
import SearchFilterBar from "../../components/common/SearchFilterBar";

function formatProviderRating(rating: number) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 2,
  }).format(rating);
}

function AdminProvidersPage() {
  const { token } = useAuth();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [availableServices, setAvailableServices] = useState<Service[]>([]);
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [providerServicesMap, setProviderServicesMap] = useState<
    Record<string, string[]>
  >({});
  const [selectedProvider, setSelectedProvider] = useState<Provider | null>(null);

  const [providerSearch, setProviderSearch] = useState("");
  const [selectedType, setSelectedType] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    loadData();
  }, [token]);

  async function loadData() {
    if (!token) return;
    setLoading(true);
    try {
      const [providersData, servicesData] = await Promise.all([
        fetchProviders(token),
        fetchServices(),
      ]);
      setProviders(providersData);
      setAvailableServices(servicesData);

      const servicesMap: Record<string, string[]> = {};
      const lookups = await Promise.allSettled(
        providersData.map(async (p) => {
          const pServices = await fetchProviderServices(p.id);
          const names = pServices
            .map(
              (ps: any) =>
                servicesData.find((s) => s.id === ps.service_id)?.name,
            )
            .filter(Boolean) as string[];
          return { id: p.id, names };
        }),
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

  const filteredProviders = useMemo(() => {
    const normalizedSearch = providerSearch.trim().toLowerCase();

    return providers.filter((provider) => {
      const specializationsText = (provider.specializations || []).join(" ");
      const providerContent =
        `${provider.name} ${provider.email} ${provider.phone ?? ""} ${provider.bio ?? ""} ${specializationsText}`.toLowerCase();

      const matchesSearch =
        !normalizedSearch || providerContent.includes(normalizedSearch);

      const matchesType =
        !selectedType ||
        provider.type.toLowerCase() === selectedType.toLowerCase();

      const matchesStatus =
        !selectedStatus ||
        provider.availability_status.toLowerCase() ===
          selectedStatus.toLowerCase();

      let matchesService = true;
      if (selectedServiceId) {
        const targetService = availableServices.find(
          (s) => s.id === selectedServiceId,
        );
        const providerServiceNames = providerServicesMap[provider.id] || [];
        matchesService = Boolean(
          targetService && providerServiceNames.includes(targetService.name),
        );
      }

      return matchesSearch && matchesType && matchesStatus && matchesService;
    });
  }, [
    providers,
    providerSearch,
    selectedType,
    selectedStatus,
    selectedServiceId,
    availableServices,
    providerServicesMap,
  ]);

  const clearProviderFilters = () => {
    setProviderSearch("");
    setSelectedType("");
    setSelectedStatus("");
    setSelectedServiceId("");
  };

  const handleEdit = async (provider: Provider) => {
    setEditingProviderId(provider.id);
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleDeactivate = async (provider: Provider) => {
    if (window.confirm("Are you sure to deactivate this account?")) {
      try {
        if (!token) return;
        await updateProvider(token, provider.id, {
          availability_status: "inactive",
        });
        loadData();
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  const handleActivate = async (provider: Provider) => {
    if (window.confirm("Are you sure to activate this account?")) {
      try {
        if (!token) return;
        await updateProvider(token, provider.id, {
          availability_status: "available",
        });
        loadData();
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  const providerColumns: ColumnDef<Provider>[] = [
    {
      header: "Provider",
      key: "provider",
      render: (provider) => (
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <UserAvatar photo={provider.photo} name={provider.name} size={40} />
          <div>
            <button
              type="button"
              className="admin-table-name-btn"
              onClick={() => setSelectedProvider(provider)}
            >
              {provider.name}
            </button>
            {provider.bio && (
              <p
                style={{
                  margin: 0,
                  fontSize: "0.85rem",
                  color: "gray",
                }}
              >
                {provider.bio.substring(0, 50)}...
              </p>
            )}
          </div>
        </div>
      ),
    },
    {
      header: "Type / Status",
      key: "type_status",
      render: (provider) => (
        <div>
          <span style={{ textTransform: "capitalize", fontWeight: 600 }}>{provider.type}</span>
          <div style={{ marginTop: "0.25rem" }}>
            <StatusBadge status={provider.availability_status} />
          </div>
        </div>
      ),
    },
    {
      header: "Rating",
      key: "rating",
      render: (provider) => (
        <>
          {provider.type === "person" &&
          provider.average_rating != null &&
          (provider.rating_count ?? 0) > 0 ? (
            <span
              className="admin-provider-rating"
              aria-label={`${formatProviderRating(provider.average_rating)} from ${provider.rating_count} reviews`}
            >
              <span aria-hidden="true">★</span>{" "}
              {formatProviderRating(provider.average_rating)} (
              {provider.rating_count})
            </span>
          ) : (
            <span className="admin-provider-rating--empty">—</span>
          )}
        </>
      ),
    },
    {
      header: "Availability",
      key: "availability",
      render: (provider) => (
        <>
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
        </>
      ),
    },
    {
      header: "Services",
      key: "services",
      render: (provider) => (
        <>
          {providerServicesMap[provider.id] &&
          providerServicesMap[provider.id].length > 0 ? (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "0.35rem",
              }}
            >
              {providerServicesMap[provider.id].map((name) => (
                <span
                  key={name}
                  className="admin-table-tag"
                >
                  {name}
                </span>
              ))}
            </div>
          ) : (
            <span style={{ color: "#94a3b8", fontSize: "0.85rem" }}>None</span>
          )}
        </>
      ),
    },
    {
      header: "User Login",
      key: "login",
      render: (provider) => (
        <>
          {provider.user_id ? (
            <span style={{ color: "green", fontSize: "0.85rem" }}>Linked</span>
          ) : (
            <span style={{ color: "gray", fontSize: "0.85rem" }}>No Login</span>
          )}
        </>
      ),
    },
    {
      header: "Actions",
      key: "actions",
      align: "center",
      render: (provider) => (
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "center" }}>
          <button
            type="button"
            className="admin-table-edit-btn"
            onClick={() => handleEdit(provider)}
          >
            ✏️ Edit
          </button>
          {provider.availability_status !== "inactive" ? (
            <button
              type="button"
              className="admin-table-edit-btn admin-table-edit-btn--danger"
              onClick={() => handleDeactivate(provider)}
            >
              Deactivate
            </button>
          ) : (
            <button
              type="button"
              className="admin-table-edit-btn admin-table-edit-btn--success"
              onClick={() => handleActivate(provider)}
            >
              Activate
            </button>
          )}
        </div>
      ),
    },
  ];

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
            } else {
              setEditingProviderId(null);
              setShowForm(true);
            }
          }}
        >
          {showForm ? "✖" : "+ Add Provider"}
        </button>
      </header>

      {showForm && (
        <ProviderForm
          token={token}
          provider={
            editingProviderId
              ? providers.find((p) => p.id === editingProviderId) || null
              : null
          }
          availableServices={availableServices}
          providerServices={
            editingProviderId && providerServicesMap[editingProviderId]
              ? availableServices
                  .filter((s) =>
                    providerServicesMap[editingProviderId].includes(s.name),
                  )
                  .map((s) => s.id)
              : []
          }
          onSubmitSuccess={() => {
            setShowForm(false);
            setEditingProviderId(null);
            loadData();
          }}
          onCancel={() => {
            setShowForm(false);
            setEditingProviderId(null);
          }}
        />
      )}

      <section className="admin-appointments-card" style={{ width: "100%" }}>
        <div className="admin-appointments-card__header">
          <div>
            <h2>Provider List</h2>
          </div>
        </div>

        {!loading && (
          <SearchFilterBar
            searchValue={providerSearch}
            onSearchChange={setProviderSearch}
            searchPlaceholder="Search providers by name, email, bio..."
            onClear={clearProviderFilters}
            resultCount={{
              current: filteredProviders.length,
              total: providers.length,
              entityName: "providers",
            }}
          >
            <label className="admin-services-filter-field">
              <span className="admin-services-filter-label">Type</span>
              <select
                value={selectedType}
                onChange={(event) => setSelectedType(event.target.value)}
                aria-label="Filter providers by type"
              >
                <option value="">All Types</option>
                <option value="person">Person</option>
                <option value="resource">Resource</option>
              </select>
            </label>

            <label className="admin-services-filter-field">
              <span className="admin-services-filter-label">Status</span>
              <select
                value={selectedStatus}
                onChange={(event) => setSelectedStatus(event.target.value)}
                aria-label="Filter providers by status"
              >
                <option value="">All Statuses</option>
                <option value="available">Available</option>
                <option value="on_leave">On Leave</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>

            <label className="admin-services-filter-field">
              <span className="admin-services-filter-label">Service</span>
              <select
                value={selectedServiceId}
                onChange={(event) => setSelectedServiceId(event.target.value)}
                aria-label="Filter providers by service"
              >
                <option value="">All Services</option>
                {availableServices.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </select>
            </label>
          </SearchFilterBar>
        )}

        <DataTable
          columns={providerColumns}
          data={filteredProviders}
          keyExtractor={(provider) => provider.id}
          loading={loading}
          loadingMessage="Loading providers..."
          error={error}
          emptyMessage="No providers found. Add a provider to get started."
          emptyContent={
            <div className="admin-services-filter-empty">
              <p className="admin-services-message">
                No providers match the selected filters.
              </p>
              <button
                type="button"
                className="admin-secondary-button"
                onClick={clearProviderFilters}
              >
                Reset Filters
              </button>
            </div>
          }
        />
      </section>

      <Modal
        isOpen={Boolean(selectedProvider)}
        onClose={() => setSelectedProvider(null)}
      >
        {selectedProvider && (
          <>
            <h3 style={{ marginTop: 0, color: "#18312f" }}>
              {selectedProvider.name}
            </h3>
            <div style={{ margin: "1.5rem 0" }}>
              <p style={{ margin: "0.5rem 0" }}>
                <strong>Email:</strong> {selectedProvider.email}
              </p>
              <p style={{ margin: "0.5rem 0" }}>
                <strong>Phone:</strong>{" "}
                {selectedProvider.phone || "Not provided"}
              </p>
            </div>
          </>
        )}
      </Modal>
    </main>
  );
}

export default AdminProvidersPage;
