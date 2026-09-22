import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/useAuth";
import {
  fetchAdminAppointments,
  type AdminAppointment,
  type AdminAppointmentListResponse,
} from "../lib/adminAppointments";

type NamedRecord = {
  id: string;
  name: string;
};

function formatAppointmentDate(dateString: string): string {
  return new Date(dateString).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function getStatusClass(status: string): string {
  return `admin-appointment-status admin-appointment-status--${status.toLowerCase()}`;
}

export default function AdminAppointmentsPage() {
  const { token } = useAuth();

  const [appointments, setAppointments] = useState<AdminAppointment[]>([]);
  const [pagination, setPagination] =
    useState<AdminAppointmentListResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [page, setPage] = useState(1);

  const [providers, setProviders] = useState<NamedRecord[]>([]);
  const [services, setServices] = useState<NamedRecord[]>([]);

  const [providerId, setProviderId] = useState("");
  const [serviceId, setServiceId] = useState("");

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const loadAppointments = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const response = await fetchAdminAppointments(token, {
        page,
        search,
        status,
        start_date: startDate,
        end_date: endDate,
        provider_id: providerId,
        service_id: serviceId,
      });

      const [providersResponse, servicesResponse] = await Promise.all([
        fetch("/api/providers"),
        fetch("/api/services"),
      ]);

      if (!providersResponse.ok || !servicesResponse.ok) {
        throw new Error("Failed to load providers or services");
      }

      const providersData: NamedRecord[] = await providersResponse.json();
      const servicesData: NamedRecord[] = await servicesResponse.json();

      setProviders(providersData);
      setServices(servicesData);

      setAppointments(response.appointments);
      setPagination(response);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load appointments",
      );
    } finally {
      setLoading(false);
      setInitialLoading(false);
    }
  }, [endDate, page, providerId, search, serviceId, startDate, status, token]);

  useEffect(() => {
    setPage(1);
  }, [endDate, providerId, search, serviceId, startDate, status]);

  useEffect(() => {
    void loadAppointments();
  }, [loadAppointments]);

  useEffect(() => {
    const loadFilterOptions = async () => {
      try {
        const [providersResponse, servicesResponse] = await Promise.all([
          fetch("/api/providers"),
          fetch("/api/services"),
        ]);

        if (!providersResponse.ok || !servicesResponse.ok) {
          throw new Error("Failed to load filter options");
        }

        const providersData: NamedRecord[] = await providersResponse.json();
        const servicesData: NamedRecord[] = await servicesResponse.json();

        setProviders(providersData);
        setServices(servicesData);
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load filter options.",
        );
      }
    };

    void loadFilterOptions();
  }, []);

  if (initialLoading) {
    return (
      <main className="admin-appointments-page">
        <p>Loading appointments...</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="admin-appointments-page">
        <p role="alert">{error}</p>
        <button type="button" onClick={() => void loadAppointments()}>
          Try again
        </button>
      </main>
    );
  }

  return (
    <main className="admin-appointments-page">
      <header className="admin-page-header">
        <div>
          <p className="admin-page-eyebrow">Administration</p>
          <h1>Appointments</h1>
          <p>Manage and review all customer appointments.</p>
        </div>
      </header>

      <section className="admin-appointments-card">
        <div className="admin-appointments-filters">
          <div className="admin-appointments-filter">
            <label htmlFor="appointment-search">Search customer</label>

            <input
              id="appointment-search"
              type="search"
              placeholder="Email or phone"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <div className="admin-appointments-filter">
            <label htmlFor="appointment-provider">Provider</label>

            <select
              id="appointment-provider"
              value={providerId}
              onChange={(event) => setProviderId(event.target.value)}
            >
              <option value="">All providers</option>

              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
          </div>

          <div className="admin-appointments-filter">
            <label htmlFor="appointment-service">Service</label>

            <select
              id="appointment-service"
              value={serviceId}
              onChange={(event) => setServiceId(event.target.value)}
            >
              <option value="">All services</option>

              {services.map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </div>

          <div className="admin-appointments-filter">
            <label htmlFor="appointment-status">Status</label>

            <select
              id="appointment-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="confirmed">Confirmed</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>

          <div className="admin-appointments-filter">
            <label htmlFor="appointment-start-date">From</label>

            <input
              id="appointment-start-date"
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </div>

          <div className="admin-appointments-filter">
            <label htmlFor="appointment-end-date">To</label>

            <input
              id="appointment-end-date"
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            setSearch("");
            setStatus("");
            setStartDate("");
            setEndDate("");
            setProviderId("");
            setServiceId("");
            setPage(1);
          }}
          className="admin-clear-filters"
        >
          Clear filters
        </button>
        <div className="admin-appointments-card__header">
          <h2>All appointments</h2>

          <span>{pagination?.total ?? 0} total appointments</span>
        </div>

        {appointments.length === 0 ? (
          <p>No appointments found.</p>
        ) : (
          <div className="admin-appointments-table-wrapper">
            <table className="admin-appointments-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Service</th>
                  <th>Provider</th>
                  <th>Appointment time</th>
                  <th>Duration</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                {appointments.map((appointment) => (
                  <tr key={appointment.id}>
                    <td>
                      <strong>{appointment.user_name}</strong>
                      <span>{appointment.user_email}</span>
                    </td>

                    <td>{appointment.service_name}</td>

                    <td>{appointment.provider_name}</td>

                    <td>
                      {formatAppointmentDate(appointment.appointment_start)}
                    </td>

                    <td>{appointment.duration_minutes} min</td>

                    <td>
                      <span className={getStatusClass(appointment.status)}>
                        {appointment.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="admin-appointments-pagination">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((currentPage) => currentPage - 1)}
            >
              Previous
            </button>

            <span>
              Page {pagination.page} of {pagination.total_pages}
            </span>

            <button
              type="button"
              disabled={page >= pagination.total_pages}
              onClick={() => setPage((currentPage) => currentPage + 1)}
            >
              Next
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
