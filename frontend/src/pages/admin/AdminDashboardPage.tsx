import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../auth/useAuth";
import DashboardStatsGrid from "../../features/admin/dashboard/DashboardStatsGrid";
import DashboardAvailabilityCalendar from "../../features/admin/dashboard/DashboardAvailabilityCalendar";
import DashboardStatusMix from "../../features/admin/dashboard/DashboardStatusMix";
import DashboardActivityTable from "../../features/admin/dashboard/DashboardActivityTable";

type Overview = {
  total_appointments: number;
  upcoming_appointments: number;
  appointments_today: number;
  appointments_by_status: { status: string; count: number }[];
  total_providers: number;
  active_providers: number;
  total_services: number;
  active_services: number;
};

type AdminAppointment = {
  id: string;
  service_id: string;
  user_name: string;
  user_email: string;
  appointment_start: string;
  duration_minutes: number;
  status: string;
  service_name: string;
  provider_name: string;
};

const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

function monthBounds() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
    label: new Intl.DateTimeFormat("en-US", {
      month: "long",
      year: "numeric",
    }).format(today),
  };
}

function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function AdminDashboardPage() {
  const { token } = useAuth();
  const month = useMemo(() => monthBounds(), []);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [appointments, setAppointments] = useState<AdminAppointment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const query = `timezone=${encodeURIComponent(timezone)}&start_date=${month.start}&end_date=${month.end}&page_size=100`;
        const authHeaders: HeadersInit = token
          ? {
              Authorization: `Bearer ${token}`,
            }
          : {};

        const [overviewResponse, appointmentsResponse, servicesResponse] =
          await Promise.all([
            fetch(
              `/api/admin/overview?timezone=${encodeURIComponent(timezone)}`,
              {
                headers: authHeaders,
              },
            ),
            fetch(`/api/admin/appointments?${query}`, {
              headers: authHeaders,
            }),
            fetch("/api/services"),
          ]);
        if (
          !overviewResponse.ok ||
          !appointmentsResponse.ok ||
          !servicesResponse.ok
        ) {
          throw new Error("Dashboard data could not be loaded.");
        }
        const appointmentsData = await appointmentsResponse.json();
        setOverview(await overviewResponse.json());
        setAppointments(appointmentsData.appointments);
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Dashboard data could not be loaded.",
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadDashboard();
  }, [month.end, month.start, token]);

  const appointmentsByDay = useMemo(
    () =>
      appointments.reduce<Record<string, number>>((counts, appointment) => {
        if (appointment.status !== "cancelled") {
          const key = dateKey(new Date(appointment.appointment_start));
          counts[key] = (counts[key] || 0) + 1;
        }
        return counts;
      }, {}),
    [appointments],
  );

  return (
    <section className="dashboard-page">
      <header className="dashboard-heading">
        <div>
          <p className="eyebrow">Operations overview</p>
          <h1>Admin dashboard</h1>
          <p className="services-intro">
            A clear read on the booking business, from today&apos;s workload to
            this month&apos;s performance.
          </p>
        </div>
        <div className="dashboard-period">
          <span>Reporting period</span>
          <strong>{month.label}</strong>
          <small>{timezone}</small>
        </div>
      </header>

      {error && (
        <div className="status-message status-message--error" role="alert">
          <strong>We could not load the dashboard.</strong>
          <span>{error}</span>
        </div>
      )}
      {isLoading && (
        <div className="dashboard-loading">Loading dashboard data...</div>
      )}

      {!isLoading && !error && overview && (
        <>
          <DashboardStatsGrid overview={overview} />
          <DashboardAvailabilityCalendar appointmentsByDay={appointmentsByDay} />
          <DashboardStatusMix overview={overview} />
          <DashboardActivityTable appointments={appointments} />
        </>
      )}
    </section>
  );
}

export default AdminDashboardPage;
