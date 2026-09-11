import { useEffect, useMemo, useState } from "react";

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

type Service = { id: string; price: string | number | null };

const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

function monthBounds() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
    label: new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(today),
  };
}

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function AdminDashboardPage() {
  const month = useMemo(() => monthBounds(), []);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [appointments, setAppointments] = useState<AdminAppointment[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const query = `timezone=${encodeURIComponent(timezone)}&start_date=${month.start}&end_date=${month.end}&page_size=100`;
        const [overviewResponse, appointmentsResponse, servicesResponse] = await Promise.all([
          fetch(`/api/admin/overview?timezone=${encodeURIComponent(timezone)}`),
          fetch(`/api/admin/appointments?${query}`),
          fetch("/api/services"),
        ]);
        if (!overviewResponse.ok || !appointmentsResponse.ok || !servicesResponse.ok) {
          throw new Error("Dashboard data could not be loaded.");
        }
        const appointmentsData = await appointmentsResponse.json();
        setOverview(await overviewResponse.json());
        setAppointments(appointmentsData.appointments);
        setServices(await servicesResponse.json());
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Dashboard data could not be loaded.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadDashboard();
  }, [month.end, month.start]);

  const monthlyStatusCount = (status: string) => appointments.filter((appointment) => appointment.status === status).length;
  const revenue = appointments.reduce((total, appointment) => {
    if (appointment.status !== "completed") return total;
    const service = services.find((item) => item.id === appointment.service_id);
    return total + Number(service?.price || 0);
  }, 0);

  return (
    <section className="dashboard-page">
      <header className="dashboard-heading">
        <div>
          <p className="eyebrow">Operations overview</p>
          <h1>Admin dashboard</h1>
          <p className="services-intro">A clear read on the booking business, from today&apos;s workload to this month&apos;s performance.</p>
        </div>
        <div className="dashboard-period"><span>Reporting period</span><strong>{month.label}</strong><small>{timezone}</small></div>
      </header>

      {error && <div className="status-message status-message--error" role="alert"><strong>We could not load the dashboard.</strong><span>{error}</span></div>}
      {isLoading && <div className="dashboard-loading">Loading dashboard data...</div>}

      {!isLoading && !error && overview && (
        <>
          <div className="dashboard-stat-grid">
            <article className="dashboard-stat dashboard-stat--accent"><span>Bookings this month</span><strong>{appointments.length}</strong><small>{overview.appointments_today} scheduled today</small></article>
            <article className="dashboard-stat"><span>Completed</span><strong>{monthlyStatusCount("completed")}</strong><small>Completed during {month.label}</small></article>
            <article className="dashboard-stat dashboard-stat--warm"><span>Cancelled</span><strong>{monthlyStatusCount("cancelled")}</strong><small>Cancelled during {month.label}</small></article>
            <article className="dashboard-stat"><span>Revenue this month</span><strong>{formatMoney(revenue)}</strong><small>Completed services only</small></article>
          </div>

          <div className="dashboard-grid">
            <section className="dashboard-panel dashboard-panel--wide">
              <div className="dashboard-panel__heading"><div><p className="panel-kicker">Booking health</p><h2>Status mix</h2></div><span className="dashboard-total">{overview.total_appointments} total</span></div>
              <div className="status-bars">
                {overview.appointments_by_status.map((item) => <div className="status-bar" key={item.status}><div><span>{item.status}</span><strong>{item.count}</strong></div><div className="status-bar__track"><i style={{ width: `${Math.max((item.count / Math.max(overview.total_appointments, 1)) * 100, 3)}%` }} /></div></div>)}
              </div>
            </section>
            <section className="dashboard-panel dashboard-panel--quiet">
              <p className="panel-kicker">Data quality</p><h2>No-show rate</h2><strong className="dashboard-unavailable">Not tracked</strong><p className="dashboard-note">Add a no-show status to appointments to measure this metric.</p>
            </section>
          </div>

          <section className="dashboard-panel dashboard-panel--table">
            <div className="dashboard-panel__heading"><div><p className="panel-kicker">Latest activity</p><h2>Appointments this month</h2></div><span className="dashboard-total">{appointments.length} bookings</span></div>
            {appointments.length === 0 ? <p className="dashboard-note">No appointments have been recorded for this month.</p> : <div className="dashboard-table-wrap"><table className="dashboard-table"><thead><tr><th>Customer</th><th>Service</th><th>Provider</th><th>When</th><th>Status</th></tr></thead><tbody>{appointments.slice(0, 8).map((appointment) => <tr key={appointment.id}><td><strong>{appointment.user_name}</strong><small>{appointment.user_email}</small></td><td>{appointment.service_name}</td><td>{appointment.provider_name}</td><td>{formatDate(appointment.appointment_start)}</td><td><span className={`dashboard-status dashboard-status--${appointment.status}`}>{appointment.status}</span></td></tr>)}</tbody></table></div>}
          </section>
        </>
      )}
    </section>
  );
}

export default AdminDashboardPage;