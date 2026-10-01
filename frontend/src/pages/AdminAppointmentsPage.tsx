import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/useAuth";
import {
  fetchAdminAppointments,
  type AdminAppointment,
  type AdminAppointmentListResponse,
} from "../lib/adminAppointments";
import AdminAppointmentsFilters, {
  NamedRecord,
} from "../features/admin/appointments/AdminAppointmentsFilters";
import AdminAppointmentsTable from "../features/admin/appointments/AdminAppointmentsTable";
import AdminAppointmentsPagination from "../features/admin/appointments/AdminAppointmentsPagination";

export default function AdminAppointmentsPage() {
  const { token } = useAuth();

  const [appointments, setAppointments] = useState<AdminAppointment[]>([]);
  const [pagination, setPagination] =
    useState<AdminAppointmentListResponse | null>(null);

  const [, setLoading] = useState(true);
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
        <AdminAppointmentsFilters
          search={search}
          setSearch={setSearch}
          providerId={providerId}
          setProviderId={setProviderId}
          serviceId={serviceId}
          setServiceId={setServiceId}
          status={status}
          setStatus={setStatus}
          startDate={startDate}
          setStartDate={setStartDate}
          endDate={endDate}
          setEndDate={setEndDate}
          providers={providers}
          services={services}
        />

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

        <AdminAppointmentsTable appointments={appointments} />

        {pagination && (
          <AdminAppointmentsPagination
            pagination={pagination}
            page={page}
            setPage={setPage}
          />
        )}
      </section>
    </main>
  );
}
