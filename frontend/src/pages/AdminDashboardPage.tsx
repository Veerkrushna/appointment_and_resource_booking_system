import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/useAuth";

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
type CalendarView = "month" | "week";
type AvailabilityStatus = "available" | "booked" | "unavailable" | "limited";

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

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "Rupees",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function getCalendarDays(date: Date, view: CalendarView) {
  const start = new Date(
    date.getFullYear(),
    date.getMonth(),
    view === "month" ? 1 : date.getDate(),
  );
  start.setDate(start.getDate() - start.getDay());
  return Array.from({ length: view === "month" ? 42 : 7 }, (_, index) => {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    return day;
  });
}

function availabilityStatus(
  date: Date,
  bookingCount: number,
): AvailabilityStatus {
  if (date.getDay() === 0 || date.getDay() === 6) return "unavailable";
  if (bookingCount >= 3) return "booked";
  if (bookingCount > 0) return "limited";
  return "available";
}

function formatCalendarLabel(date: Date, view: CalendarView) {
  if (view === "week") {
    const weekEnd = new Date(date);
    weekEnd.setDate(date.getDate() + 6);
    return `${new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date)} - ${new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(weekEnd)}`;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    year: "numeric",
  }).format(date);
}

function AdminDashboardPage() {
  const { token } = useAuth();
  const month = useMemo(() => monthBounds(), []);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [appointments, setAppointments] = useState<AdminAppointment[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [calendarView, setCalendarView] = useState<CalendarView>("month");
  const [calendarDate, setCalendarDate] = useState(() => new Date());
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
        setServices(await servicesResponse.json());
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

  const monthlyStatusCount = (status: string) =>
    appointments.filter((appointment) => appointment.status === status).length;
  const revenue = appointments.reduce((total, appointment) => {
    if (appointment.status !== "completed") return total;
    const service = services.find((item) => item.id === appointment.service_id);
    return total + Number(service?.price || 0);
  }, 0);
  const calendarDays = useMemo(
    () => getCalendarDays(calendarDate, calendarView),
    [calendarDate, calendarView],
  );
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

  function moveCalendar(amount: number) {
    setCalendarDate((current) => {
      const next = new Date(current);
      next.setDate(
        current.getDate() +
          (calendarView === "month" ? amount * 31 : amount * 7),
      );
      return next;
    });
  }

  const statusCount = (status: string) =>
    overview?.appointments_by_status.find(
      (item) => item.status.toLowerCase() === status,
    )?.count ?? 0;

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
          <div className="dashboard-stat-grid">
            <article className="dashboard-stat dashboard-stat--accent">
              <span>Total bookings</span>
              <strong>{overview.total_appointments}</strong>
              <small>{overview.appointments_today} scheduled today</small>
            </article>

            <article className="dashboard-stat">
              <span>Upcoming appointments</span>
              <strong>{overview.upcoming_appointments}</strong>
              <small>Confirmed and pending future appointments</small>
            </article>

            <article className="dashboard-stat">
              <span>Completed</span>
              <strong>{statusCount("completed")}</strong>
              <small>Completed appointments</small>
            </article>

            <article className="dashboard-stat dashboard-stat--warm">
              <span>Cancelled</span>
              <strong>{statusCount("cancelled")}</strong>
              <small>Cancelled appointments</small>
            </article>

            <article className="dashboard-stat">
              <span>Total providers</span>
              <strong>{overview.total_providers}</strong>
              <small>{overview.active_providers} active providers</small>
            </article>

            <article className="dashboard-stat">
              <span>Total services</span>
              <strong>{overview.total_services}</strong>
              <small>{overview.active_services} active services</small>
            </article>
          </div>

          <section className="dashboard-panel availability-widget">
            <div className="dashboard-panel__heading availability-widget__heading">
              <div>
                <p className="panel-kicker">Capacity planning</p>
                <h2>Availability calendar</h2>
              </div>
              <div className="availability-widget__controls">
                <div
                  className="availability-view-toggle"
                  role="group"
                  aria-label="Calendar view"
                >
                  {(["month", "week"] as CalendarView[]).map((view) => (
                    <button
                      className={calendarView === view ? "active" : ""}
                      key={view}
                      type="button"
                      aria-pressed={calendarView === view}
                      onClick={() => setCalendarView(view)}
                    >
                      {view}
                    </button>
                  ))}
                </div>
                <button
                  className="calendar-nav"
                  type="button"
                  aria-label="Previous period"
                  onClick={() => moveCalendar(-1)}
                >
                  &#8592;
                </button>
                <button
                  className="calendar-nav"
                  type="button"
                  aria-label="Next period"
                  onClick={() => moveCalendar(1)}
                >
                  &#8594;
                </button>
              </div>
            </div>
            <div className="availability-widget__meta">
              <strong>
                {formatCalendarLabel(calendarDays[0], calendarView)}
              </strong>
              <div className="availability-legend">
                {(
                  [
                    "available",
                    "booked",
                    "unavailable",
                    "limited",
                  ] as AvailabilityStatus[]
                ).map((status) => (
                  <span key={status}>
                    <i
                      className={`availability-swatch availability-swatch--${status}`}
                    />
                    {status}
                  </span>
                ))}
              </div>
            </div>
            <div
              className={`availability-calendar availability-calendar--${calendarView}`}
              role="grid"
              aria-label={`${formatCalendarLabel(calendarDays[0], calendarView)} availability`}
            >
              {calendarDays.map((day) => {
                const count = appointmentsByDay[dateKey(day)] || 0;
                const status = availabilityStatus(day, count);
                const isCurrentMonth =
                  day.getMonth() === calendarDate.getMonth();
                return (
                  <div
                    className={`availability-day availability-day--${status}${calendarView === "month" && !isCurrentMonth ? " availability-day--outside" : ""}`}
                    key={dateKey(day)}
                    role="gridcell"
                    aria-label={`${day.toLocaleDateString("en-US", { month: "long", day: "numeric" })}: ${status}`}
                  >
                    <span>
                      {calendarView === "week" && (
                        <small>
                          {new Intl.DateTimeFormat("en-US", {
                            weekday: "short",
                          }).format(day)}
                        </small>
                      )}
                      {day.getDate()}
                    </span>
                    {count > 0 && (
                      <strong>
                        {count} {count === 1 ? "booking" : "bookings"}
                      </strong>
                    )}
                    <em>{status}</em>
                  </div>
                );
              })}
            </div>
          </section>

          <div className="dashboard-grid">
            <section className="dashboard-panel dashboard-panel--wide">
              <div className="dashboard-panel__heading">
                <div>
                  <p className="panel-kicker">Booking health</p>
                  <h2>Status mix</h2>
                </div>
                <span className="dashboard-total">
                  {overview.total_appointments} total
                </span>
              </div>
              <div className="status-bars">
                {overview.appointments_by_status.map((item) => (
                  <div className="status-bar" key={item.status}>
                    <div>
                      <span>{item.status}</span>
                      <strong>{item.count}</strong>
                    </div>
                    <div className="status-bar__track">
                      <i
                        style={{
                          width: `${Math.max((item.count / Math.max(overview.total_appointments, 1)) * 100, 3)}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>
            <section className="dashboard-panel dashboard-panel--quiet">
              <p className="panel-kicker">Data quality</p>
              <h2>No-show rate</h2>
              <strong className="dashboard-unavailable">Not tracked</strong>
              <p className="dashboard-note">
                Add a no-show status to appointments to measure this metric.
              </p>
            </section>
          </div>

          <section className="dashboard-panel dashboard-panel--table">
            <div className="dashboard-panel__heading">
              <div>
                <p className="panel-kicker">Latest activity</p>
                <h2>Appointments this month</h2>
              </div>
              <span className="dashboard-total">
                {appointments.length} bookings
              </span>
            </div>
            {appointments.length === 0 ? (
              <p className="dashboard-note">
                No appointments have been recorded for this month.
              </p>
            ) : (
              <div className="dashboard-table-wrap">
                <table className="dashboard-table">
                  <thead>
                    <tr>
                      <th>Customer</th>
                      <th>Service</th>
                      <th>Provider</th>
                      <th>When</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {appointments.slice(0, 8).map((appointment) => (
                      <tr key={appointment.id}>
                        <td>
                          <strong>{appointment.user_name}</strong>
                          <small>{appointment.user_email}</small>
                        </td>
                        <td>{appointment.service_name}</td>
                        <td>{appointment.provider_name}</td>
                        <td>{formatDate(appointment.appointment_start)}</td>
                        <td>
                          <span
                            className={`dashboard-status dashboard-status--${appointment.status}`}
                          >
                            {appointment.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}

export default AdminDashboardPage;
