import type { ChangeEvent, FormEvent } from "react";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "../auth/useAuth";

type Service = {
  id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  price: string | number | null;
  category: string;
  capacity?: number;
  buffer_time_minutes?: number | null;
  status: "active" | "inactive";
  providers: ServiceProviderSummary[];
};

type ServiceProviderSummary = {
  provider_id: string;
  provider_name: string;
};

type Provider = {
  id: string;
  name: string;
  type: "PERSON" | "RESOURCE";
  availability_status: "AVAILABLE" | "ON_LEAVE" | "INACTIVE";
};

const initialServiceForm = {
  name: "",
  description: "",
  category: "",
  duration_minutes: "",
  price: "",
  capacity: "1",
  buffer_time_minutes: "",
  status: "active" as "active" | "inactive",
  provider_ids: [] as string[],
};

function AdminServicesPage() {
  const { token } = useAuth();

  const [services, setServices] = useState<Service[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [isCreateFormOpen, setIsCreateFormOpen] = useState(false);
  const [editingServiceId, setEditingServiceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [updatingServiceIds, setUpdatingServiceIds] = useState<Set<string>>(
    new Set(),
  );
  const [providersServiceId, setProvidersServiceId] = useState<string | null>(
    null,
  );
  const [serviceSearch, setServiceSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [error, setError] = useState("");
  const [isProviderDropdownOpen, setIsProviderDropdownOpen] = useState(false);
  const [validationErrors, setValidationErrors] = useState<
    Record<string, string>
  >({});

  const formRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isCreateFormOpen && editingServiceId && formRef.current) {
      formRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [isCreateFormOpen, editingServiceId]);

  useEffect(() => {
    if (!providersServiceId) {
      return;
    }

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setProvidersServiceId(null);
      }
    };

    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [providersServiceId]);

  const [serviceForm, setServiceForm] = useState(initialServiceForm);

  const selectedProviders = providers.filter((provider) =>
    serviceForm.provider_ids.includes(provider.id),
  );

  const categories = [
    ...new Set(services.map((service) => service.category)),
  ].sort((firstCategory, secondCategory) =>
    firstCategory.localeCompare(secondCategory),
  );
  const normalizedSearch = serviceSearch.trim().toLowerCase();
  const filteredServices = services.filter((service) => {
    const matchesSearch =
      !normalizedSearch ||
      `${service.name} ${service.description ?? ""}`
        .toLowerCase()
        .includes(normalizedSearch);
    const matchesCategory =
      !selectedCategory || service.category === selectedCategory;
    const matchesStatus = !selectedStatus || service.status === selectedStatus;
    const matchesProvider =
      !selectedProviderId ||
      service.providers.some(
        (provider) => provider.provider_id === selectedProviderId,
      );

    return matchesSearch && matchesCategory && matchesStatus && matchesProvider;
  });

  const clearServiceFilters = () => {
    setServiceSearch("");
    setSelectedCategory("");
    setSelectedStatus("");
    setSelectedProviderId("");
  };

  const validateServiceForm = () => {
    const nextErrors: Record<string, string> = {};

    const trimmedName = serviceForm.name.trim();
    const trimmedCategory = serviceForm.category.trim();
    const trimmedDuration = serviceForm.duration_minutes.trim();
    const trimmedPrice = serviceForm.price.trim();
    const trimmedCapacity = serviceForm.capacity.trim();
    const trimmedBufferTime = serviceForm.buffer_time_minutes.trim();

    if (!trimmedName) {
      nextErrors.name = "Service name is required.";
    } else if (trimmedName.length < 3) {
      nextErrors.name = "Service name must be at least 3 characters.";
    }

    if (!trimmedCategory) {
      nextErrors.category = "Category is required.";
    }

    if (!trimmedDuration) {
      nextErrors.duration_minutes = "Duration is required.";
    } else {
      const durationValue = Number(trimmedDuration);

      if (!Number.isInteger(durationValue) || durationValue <= 0) {
        nextErrors.duration_minutes =
          "Duration must be a whole number greater than 0.";
      }
    }

    if (trimmedPrice !== "") {
      const priceValue = Number(trimmedPrice);

      if (!Number.isFinite(priceValue) || priceValue < 0) {
        nextErrors.price =
          "Price must be a valid number greater than or equal to 0.";
      }
    }

    if (!trimmedCapacity) {
      nextErrors.capacity = "Capacity is required.";
    } else {
      const capacityValue = Number(trimmedCapacity);

      if (!Number.isInteger(capacityValue) || capacityValue <= 0) {
        nextErrors.capacity = "Capacity must be a whole number greater than 0.";
      }
    }

    if (trimmedBufferTime !== "") {
      const bufferValue = Number(trimmedBufferTime);

      if (!Number.isInteger(bufferValue) || bufferValue < 0) {
        nextErrors.buffer_time_minutes =
          "Buffer time must be a whole number greater than or equal to 0.";
      }
    }

    return nextErrors;
  };

  const clearValidationError = (fieldName: string) => {
    setValidationErrors((previousErrors) => {
      if (!(fieldName in previousErrors)) {
        return previousErrors;
      }

      const nextErrors = { ...previousErrors };
      delete nextErrors[fieldName];
      return nextErrors;
    });
  };

  const handleServiceFormChange = (
    event: ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >,
  ) => {
    const { name, value } = event.target;

    setServiceForm((previousForm) => ({
      ...previousForm,
      [name]: value,
    }));

    if (validationErrors[name]) {
      clearValidationError(name);
    }
  };

  const handleProviderSelection = (providerId: string) => {
    setServiceForm((previousForm) => {
      const isSelected = previousForm.provider_ids.includes(providerId);

      return {
        ...previousForm,
        provider_ids: isSelected
          ? previousForm.provider_ids.filter((id) => id !== providerId)
          : [...previousForm.provider_ids, providerId],
      };
    });
  };

  const handleCancel = () => {
    setServiceForm(initialServiceForm);
    setEditingServiceId(null);
    setValidationErrors({});
    setIsProviderDropdownOpen(false);
    setIsCreateFormOpen(false);
  };

  const handleEditService = (service: Service) => {
    setEditingServiceId(service.id);
    setServiceForm({
      name: service.name,
      description: service.description ?? "",
      category: service.category,
      duration_minutes: String(service.duration_minutes),
      price:
        service.price !== null && service.price !== undefined
          ? String(service.price)
          : "",
      capacity:
        service.capacity !== null && service.capacity !== undefined
          ? String(service.capacity)
          : "1",
      buffer_time_minutes:
        service.buffer_time_minutes !== null &&
        service.buffer_time_minutes !== undefined
          ? String(service.buffer_time_minutes)
          : "",
      status: service.status,
      provider_ids: [],
    });
    setValidationErrors({});
    setError("");
    setIsProviderDropdownOpen(false);
    setIsCreateFormOpen(true);
  };

  const handleSubmitService = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const nextErrors = validateServiceForm();

    if (Object.keys(nextErrors).length > 0) {
      setValidationErrors(nextErrors);
      return;
    }

    try {
      setError("");
      setValidationErrors({});

      const servicePayload = {
        name: serviceForm.name.trim(),
        description: serviceForm.description.trim() || null,
        category: serviceForm.category.trim(),
        duration_minutes: Number(serviceForm.duration_minutes),
        price:
          serviceForm.price.trim() === "" ? null : Number(serviceForm.price),
        capacity: Number(serviceForm.capacity),
        buffer_time_minutes:
          serviceForm.buffer_time_minutes.trim() === ""
            ? null
            : Number(serviceForm.buffer_time_minutes),
        status: serviceForm.status,
      };

      if (editingServiceId !== null) {
        const updateResponse = await fetch(
          `/api/services/${editingServiceId}`,
          {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify(servicePayload),
          },
        );

        if (!updateResponse.ok) {
          const errorData = await updateResponse.json().catch(() => null);

          throw new Error(errorData?.detail || "Failed to update service");
        }

        const updatedService: Service = await updateResponse.json();

        setServices((previousServices) =>
          previousServices.map((service) =>
            service.id === updatedService.id
              ? { ...updatedService, providers: service.providers }
              : service,
          ),
        );
        setServiceForm(initialServiceForm);
        setEditingServiceId(null);
        setValidationErrors({});
        setIsProviderDropdownOpen(false);
        setIsCreateFormOpen(false);
      } else {
        const serviceResponse = await fetch("/api/services", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(servicePayload),
        });

        if (!serviceResponse.ok) {
          const errorData = await serviceResponse.json().catch(() => null);

          throw new Error(errorData?.detail || "Failed to create service");
        }

        const createdService: Service = await serviceResponse.json();

        if (serviceForm.provider_ids.length > 0) {
          const providerResponse = await fetch(
            `/api/services/${createdService.id}/providers`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({
                provider_ids: serviceForm.provider_ids,
              }),
            },
          );

          if (!providerResponse.ok) {
            const errorData = await providerResponse.json().catch(() => null);

            throw new Error(
              errorData?.detail ||
                "Service created, but provider assignment failed",
            );
          }
        }

        setServices((previousServices) => [
          ...previousServices,
          {
            ...createdService,
            providers: serviceForm.provider_ids.flatMap((providerId) => {
              const provider = providers.find(
                (candidate) => candidate.id === providerId,
              );
              return provider
                ? [{ provider_id: provider.id, provider_name: provider.name }]
                : [];
            }),
          },
        ]);
        setServiceForm(initialServiceForm);
        setEditingServiceId(null);
        setValidationErrors({});
        setIsProviderDropdownOpen(false);
        setIsCreateFormOpen(false);
      }
    } catch (error) {
      console.error(
        editingServiceId
          ? "Error updating service:"
          : "Error creating service:",
        error,
      );

      setError(
        error instanceof Error
          ? error.message
          : editingServiceId
            ? "Unable to update service. Please try again."
            : "Unable to create service. Please try again.",
      );
    }
  };

  const handleToggleServiceStatus = async (service: Service) => {
    const nextStatus = service.status === "active" ? "inactive" : "active";

    if (
      nextStatus === "inactive" &&
      !window.confirm(`Deactivate "${service.name}"?`)
    ) {
      return;
    }

    setUpdatingServiceIds((previousIds) =>
      new Set(previousIds).add(service.id),
    );
    setError("");

    try {
      const response = await fetch(`/api/services/${service.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ status: nextStatus }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || "Failed to update service status");
      }

      const updatedService: Service = await response.json();
      setServices((previousServices) =>
        previousServices.map((previousService) =>
          previousService.id === updatedService.id
            ? { ...updatedService, providers: previousService.providers }
            : previousService,
        ),
      );
    } catch (error) {
      console.error("Error updating service status:", error);
      setError(
        error instanceof Error
          ? error.message
          : "Unable to update service status. Please try again.",
      );
    } finally {
      setUpdatingServiceIds((previousIds) => {
        const nextIds = new Set(previousIds);
        nextIds.delete(service.id);
        return nextIds;
      });
    }
  };

  useEffect(() => {
    const loadServicesAndProviders = async () => {
      try {
        setIsLoading(true);
        setError("");

        const [servicesResponse, providersResponse] = await Promise.all([
          fetch("/api/services/admin-with-providers", {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch("/api/providers"),
        ]);

        if (!servicesResponse.ok) {
          throw new Error("Failed to fetch services");
        }

        if (!providersResponse.ok) {
          throw new Error("Failed to fetch providers");
        }

        const servicesData: Service[] = await servicesResponse.json();
        const providersData: Provider[] = await providersResponse.json();

        setServices(servicesData);
        setProviders(providersData);
      } catch (error) {
        console.error("Error fetching services and providers:", error);
        setError("Unable to load services and providers. Please try again.");
      } finally {
        setIsLoading(false);
      }
    };

    loadServicesAndProviders();
  }, [token]);

  const providersService = services.find(
    (service) => service.id === providersServiceId,
  );

  return (
    <main className="admin-services-page">
      <header className="admin-page-header">
        <div>
          <p className="admin-page-eyebrow">Administration</p>

          <h1>Services</h1>

          <p>Manage the services available in the booking system.</p>
        </div>
        <button
          type="button"
          className="admin-primary-button"
          onClick={() => {
            setServiceForm(initialServiceForm);
            setEditingServiceId(null);
            setValidationErrors({});
            setError("");
            setIsProviderDropdownOpen(false);
            setIsCreateFormOpen(true);
          }}
        >
          + Create Service
        </button>
      </header>

      {isCreateFormOpen && (
        <section ref={formRef} className="admin-appointments-card">
          <div className="admin-appointments-card__header">
            <div>
              <h2>{editingServiceId ? "Edit Service" : "Create Service"}</h2>

              <p>
                {editingServiceId
                  ? "Update service details."
                  : "Add a new service to the booking system."}
              </p>
            </div>

            <button
              type="button"
              className="admin-secondary-button"
              onClick={handleCancel}
            >
              Cancel
            </button>
          </div>
          <form className="admin-service-form" onSubmit={handleSubmitService}>
            <div className="admin-form-field">
              <label htmlFor="service-name">Service Name</label>

              <input
                id="service-name"
                name="name"
                type="text"
                placeholder="Enter service name"
                value={serviceForm.name}
                onChange={handleServiceFormChange}
                required
                aria-invalid={Boolean(validationErrors.name)}
                aria-describedby={
                  validationErrors.name ? "service-name-error" : undefined
                }
              />

              {validationErrors.name && (
                <span
                  id="service-name-error"
                  role="alert"
                  className="admin-form-error"
                >
                  {validationErrors.name}
                </span>
              )}
            </div>

            <div className="admin-form-field">
              <label htmlFor="service-description">Description</label>

              <textarea
                id="service-description"
                name="description"
                placeholder="Enter service description"
                value={serviceForm.description}
                onChange={handleServiceFormChange}
                rows={4}
                aria-invalid={Boolean(validationErrors.description)}
                aria-describedby={
                  validationErrors.description
                    ? "service-description-error"
                    : undefined
                }
              />

              {validationErrors.description && (
                <span
                  id="service-description-error"
                  role="alert"
                  className="admin-form-error"
                >
                  {validationErrors.description}
                </span>
              )}
            </div>

            <div className="admin-form-field">
              <label htmlFor="service-category">Category</label>

              <input
                id="service-category"
                name="category"
                type="text"
                placeholder="Enter service category"
                value={serviceForm.category}
                onChange={handleServiceFormChange}
                required
                aria-invalid={Boolean(validationErrors.category)}
                aria-describedby={
                  validationErrors.category
                    ? "service-category-error"
                    : undefined
                }
              />

              {validationErrors.category && (
                <span
                  id="service-category-error"
                  role="alert"
                  className="admin-form-error"
                >
                  {validationErrors.category}
                </span>
              )}
            </div>

            <div className="admin-form-row">
              <div className="admin-form-field">
                <label htmlFor="service-duration">Duration (minutes)</label>

                <input
                  id="service-duration"
                  name="duration_minutes"
                  type="number"
                  min="1"
                  placeholder="30"
                  value={serviceForm.duration_minutes}
                  onChange={handleServiceFormChange}
                  required
                  aria-invalid={Boolean(validationErrors.duration_minutes)}
                  aria-describedby={
                    validationErrors.duration_minutes
                      ? "service-duration-error"
                      : undefined
                  }
                />

                {validationErrors.duration_minutes && (
                  <span
                    id="service-duration-error"
                    role="alert"
                    className="admin-form-error"
                  >
                    {validationErrors.duration_minutes}
                  </span>
                )}
              </div>

              <div className="admin-form-field">
                <label htmlFor="service-price">Price</label>

                <input
                  id="service-price"
                  name="price"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="500"
                  value={serviceForm.price}
                  onChange={handleServiceFormChange}
                  aria-invalid={Boolean(validationErrors.price)}
                  aria-describedby={
                    validationErrors.price ? "service-price-error" : undefined
                  }
                />

                {validationErrors.price && (
                  <span
                    id="service-price-error"
                    role="alert"
                    className="admin-form-error"
                  >
                    {validationErrors.price}
                  </span>
                )}
              </div>
            </div>

            <div className="admin-form-field">
              <label htmlFor="service-capacity">Capacity</label>

              <input
                id="service-capacity"
                name="capacity"
                type="number"
                min="1"
                step="1"
                placeholder="1"
                value={serviceForm.capacity}
                onChange={handleServiceFormChange}
                required
                aria-invalid={Boolean(validationErrors.capacity)}
                aria-describedby={
                  validationErrors.capacity
                    ? "service-capacity-error"
                    : undefined
                }
              />

              {validationErrors.capacity && (
                <span
                  id="service-capacity-error"
                  role="alert"
                  className="admin-form-error"
                >
                  {validationErrors.capacity}
                </span>
              )}
            </div>

            <div className="admin-form-field">
              <label htmlFor="service-buffer-time">Buffer Time (minutes)</label>

              <input
                id="service-buffer-time"
                name="buffer_time_minutes"
                type="number"
                min="0"
                step="1"
                placeholder="10"
                value={serviceForm.buffer_time_minutes}
                onChange={handleServiceFormChange}
                aria-invalid={Boolean(validationErrors.buffer_time_minutes)}
                aria-describedby={
                  validationErrors.buffer_time_minutes
                    ? "service-buffer-time-error"
                    : undefined
                }
              />

              {validationErrors.buffer_time_minutes && (
                <span
                  id="service-buffer-time-error"
                  role="alert"
                  className="admin-form-error"
                >
                  {validationErrors.buffer_time_minutes}
                </span>
              )}
            </div>

            <div className="admin-form-field">
              <label htmlFor="service-status">Status</label>

              <select
                id="service-status"
                name="status"
                value={serviceForm.status}
                onChange={handleServiceFormChange}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>

            {!editingServiceId && (
              <div className="admin-form-field">
                <label htmlFor="provider-selection">
                  Assign Providers (Optional)
                </label>

                <div className="admin-provider-dropdown">
                  <button
                    id="provider-selection"
                    type="button"
                    className="admin-provider-dropdown__trigger"
                    onClick={() =>
                      setIsProviderDropdownOpen((isOpen) => !isOpen)
                    }
                    aria-expanded={isProviderDropdownOpen}
                  >
                    <span>
                      {selectedProviders.length === 0
                        ? "Select providers"
                        : `${selectedProviders.length} provider${
                            selectedProviders.length > 1 ? "s" : ""
                          } selected`}
                    </span>

                    <span aria-hidden="true">
                      {isProviderDropdownOpen ? "▲" : "▼"}
                    </span>
                  </button>

                  {isProviderDropdownOpen && (
                    <div className="admin-provider-dropdown__menu">
                      {providers.length === 0 ? (
                        <p className="admin-services-message">
                          No providers available.
                        </p>
                      ) : (
                        providers.map((provider) => (
                          <label
                            key={provider.id}
                            className="admin-provider-dropdown__option"
                          >
                            <input
                              type="checkbox"
                              checked={serviceForm.provider_ids.includes(
                                provider.id,
                              )}
                              onChange={() =>
                                handleProviderSelection(provider.id)
                              }
                            />

                            <span className="admin-provider-dropdown__details">
                              <strong>{provider.name}</strong>

                              <small>
                                {provider.type} · {provider.availability_status}
                              </small>
                            </span>
                          </label>
                        ))
                      )}
                    </div>
                  )}
                </div>

                {selectedProviders.length > 0 && (
                  <div className="admin-provider-dropdown__selected">
                    {selectedProviders.map((provider) => (
                      <span
                        key={provider.id}
                        className="admin-provider-dropdown__tag"
                      >
                        {provider.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="admin-service-form__actions">
              <button
                type="button"
                className="admin-secondary-button"
                onClick={handleCancel}
              >
                Cancel
              </button>

              <button type="submit" className="admin-primary-button">
                {editingServiceId ? "Save Changes" : "Create Service"}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="admin-appointments-card">
        <div className="admin-appointments-card__header">
          <div>
            <h2>Service management</h2>

            <p>View and manage all services available for booking.</p>
          </div>
        </div>

        {!isLoading && (
          <div className="admin-services-filters">
            <label className="admin-services-filter-field admin-services-filter-field--search">
              <span className="admin-services-filter-label">Search</span>
              <input
                type="search"
                placeholder="Search services..."
                value={serviceSearch}
                onChange={(event) => setServiceSearch(event.target.value)}
                aria-label="Search services by name or description"
              />
            </label>

            <label className="admin-services-filter-field">
              <span className="admin-services-filter-label">Category</span>
              <select
                value={selectedCategory}
                onChange={(event) => setSelectedCategory(event.target.value)}
                aria-label="Filter services by category"
              >
                <option value="">All Categories</option>
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>

            <label className="admin-services-filter-field">
              <span className="admin-services-filter-label">Status</span>
              <select
                value={selectedStatus}
                onChange={(event) => setSelectedStatus(event.target.value)}
                aria-label="Filter services by status"
              >
                <option value="">All Statuses</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>

            <label className="admin-services-filter-field">
              <span className="admin-services-filter-label">Provider</span>
              <select
                value={selectedProviderId}
                onChange={(event) => setSelectedProviderId(event.target.value)}
                aria-label="Filter services by provider"
              >
                <option value="">All Providers</option>
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              className="admin-secondary-button admin-services-clear-filters"
              onClick={clearServiceFilters}
            >
              Clear Filters
            </button>
          </div>
        )}

        {!isLoading && (
          <p className="admin-services-result-count" aria-live="polite">
            Showing {filteredServices.length} of {services.length} services
          </p>
        )}

        {isLoading && (
          <p className="admin-services-message">Loading services...</p>
        )}

        {!isLoading && error && (
          <p className="admin-services-message admin-services-message--error">
            {error}
          </p>
        )}

        {!isLoading && !error && services.length === 0 && (
          <p className="admin-services-message">No services found.</p>
        )}

        {!isLoading && services.length > 0 && filteredServices.length === 0 && (
          <div className="admin-services-filter-empty">
            <p className="admin-services-message">
              No services match your filters.
            </p>
            <button
              type="button"
              className="admin-secondary-button"
              onClick={clearServiceFilters}
            >
              Clear Filters
            </button>
          </div>
        )}

        {!isLoading && filteredServices.length > 0 && (
          <div className="admin-services-table-wrapper">
            <table className="admin-services-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Duration</th>
                  <th>Price</th>
                  <th>Providers</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {filteredServices.map((service) => (
                  <tr key={service.id}>
                    <td>
                      <strong>{service.name}</strong>

                      {service.description && <p>{service.description}</p>}
                    </td>

                    <td>{service.category}</td>

                    <td>{service.duration_minutes} min</td>

                    <td>
                      {service.price !== null ? `₹${service.price}` : "—"}
                    </td>

                    <td>
                      {service.providers.length === 0 ? (
                        <span>No providers</span>
                      ) : (
                        <button
                          type="button"
                          className="admin-service-provider-count"
                          onClick={() => setProvidersServiceId(service.id)}
                          aria-haspopup="dialog"
                        >
                          {service.providers.length} provider
                          {service.providers.length === 1 ? "" : "s"}
                        </button>
                      )}
                    </td>

                    <td>
                      <span
                        className={`service-status service-status--${service.status}`}
                      >
                        {service.status}
                      </span>
                    </td>

                    <td>
                      <button
                        type="button"
                        className="admin-service-action-button"
                        onClick={() => handleEditService(service)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="admin-service-action-button"
                        onClick={() => handleToggleServiceStatus(service)}
                        disabled={updatingServiceIds.has(service.id)}
                      >
                        {updatingServiceIds.has(service.id)
                          ? "Updating..."
                          : service.status === "active"
                            ? "Deactivate"
                            : "Activate"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {providersService && (
        <div
          className="admin-service-providers-backdrop"
          onClick={() => setProvidersServiceId(null)}
        >
          <section
            className="admin-service-providers-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-service-providers-title"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="admin-service-providers-dialog__header">
              <h2 id="admin-service-providers-title">
                Providers for {providersService.name}
              </h2>
              <button
                type="button"
                className="admin-service-providers-dialog__close"
                onClick={() => setProvidersServiceId(null)}
                aria-label="Close providers dialog"
              >
                ×
              </button>
            </header>
            <ul className="admin-service-providers-list">
              {providersService.providers.map((provider) => (
                <li key={provider.provider_id}>{provider.provider_name}</li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </main>
  );
}

export default AdminServicesPage;
