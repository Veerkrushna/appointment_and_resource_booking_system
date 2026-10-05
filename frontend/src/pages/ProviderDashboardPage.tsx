import { useState, useEffect, useMemo } from "react";
import { useAuth } from "../auth/useAuth";
import ProviderCalendarWidget from "../components/ProviderCalendarWidget";

type RealAppointment = {
  id: string;
  user_name: string;
  service_id: string;
  service_name?: string;
  appointment_start: string;
  status: "confirmed" | "cancelled" | "completed" | "in_progress";
};

type Service = {
  id: string;
  name: string;
};

export default function ProviderDashboardPage() {
  const { customer, token } = useAuth();
  const [appointments, setAppointments] = useState<RealAppointment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      if (!customer?.provider_id || !token) {
        setIsLoading(false);
        return;
      }
      try {
        const [aptRes, servicesRes] = await Promise.all([
          fetch(
            `/api/appointments?provider_id=${customer.provider_id}&page_size=100`,
            {
              headers: { Authorization: `Bearer ${token}` },
            },
          ),
          fetch(`/api/services`),
        ]);

        if (!aptRes.ok) throw new Error("Failed to fetch appointments");
        if (!servicesRes.ok) throw new Error("Failed to fetch services");

        const aptData = await aptRes.json();
        const servicesData: Service[] = await servicesRes.json();

        const mappedAppointments = (aptData.appointments || []).map(
          (apt: any) => {
            const service = servicesData.find((s) => s.id === apt.service_id);
            return {
              ...apt,
              service_name: service ? service.name : "Unknown Service",
            };
          },
        );

        setAppointments(mappedAppointments);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [customer?.provider_id, token]);

  const stats = useMemo(() => {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");
    const todayStr = `${year}-${month}-${day}`;
    const sevenDaysFromNow = new Date();
    sevenDaysFromNow.setDate(today.getDate() + 7);

    let todayCount = 0;
    let remainingToday = 0;
    let upcomingCount = 0;
    let completedCount = 0;

    appointments.forEach((apt) => {
      const aptDate = new Date(apt.appointment_start);
      const aptYear = aptDate.getFullYear();
      const aptMonth = String(aptDate.getMonth() + 1).padStart(2, "0");
      const aptDay = String(aptDate.getDate()).padStart(2, "0");
      const aptDateStr = `${aptYear}-${aptMonth}-${aptDay}`;

      if (apt.status === "completed") {
        completedCount++;
      }

      if (apt.status !== "cancelled" && apt.status !== "completed") {
        if (aptDateStr === todayStr) {
          todayCount++;
          if (aptDate > today) {
            remainingToday++;
          }
        }
        if (aptDate > today && aptDate <= sevenDaysFromNow) {
          upcomingCount++;
        }
      }
    });

    return {
      today: todayCount,
      upcoming: upcomingCount,
      completed: completedCount,
      remainingToday: remainingToday,
    };
  }, [appointments]);

  const todaysAppointments = useMemo(() => {
    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    return appointments
      .filter((apt) => {
        const aptDate = new Date(apt.appointment_start);
        const aptDateStr = `${aptDate.getFullYear()}-${String(aptDate.getMonth() + 1).padStart(2, "0")}-${String(aptDate.getDate()).padStart(2, "0")}`;
        return aptDateStr === todayStr && apt.status !== "cancelled";
      })
      .sort(
        (a, b) =>
          new Date(a.appointment_start).getTime() -
          new Date(b.appointment_start).getTime(),
      );
  }, [appointments]);

  if (isLoading) {
    return (
      <section className="dashboard-page">
        <div className="dashboard-loading">Loading your dashboard...</div>
      </section>
    );
  }

  return (
    <section className="dashboard-page">
      <header className="dashboard-heading">
        <div>
          <p className="eyebrow">Welcome back, {customer?.name}</p>
          <h1>Provider Dashboard</h1>
          <p className="services-intro">
            Here is an overview of your schedule and appointments.
          </p>
        </div>
      </header>

      {error && (
        <div style={{ color: "red", marginBottom: "1rem" }}>{error}</div>
      )}

      <div
        className="dashboard-stat-grid"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
      >
        <article className="dashboard-stat dashboard-stat--accent">
          <span>Today's appointment</span>
          <strong>{stats.today}</strong>
          <small>Total scheduled today</small>
        </article>
        <article className="dashboard-stat">
          <span>remaining today</span>
          <strong>{stats.remainingToday}</strong>
          <small>Appointments left</small>
        </article>
        <article className="dashboard-stat dashboard-stat--upcoming">
          <span>upcoming appointment</span>
          <strong>{stats.upcoming}</strong>
          <small>In the next 7 days</small>
        </article>
        <article className="dashboard-stat dashboard-stat--completed">
          <span>completed</span>
          <strong>{stats.completed}</strong>
          <small>Total completed</small>
        </article>
      </div>

      <section
        className="dashboard-panel dashboard-panel--table"
        style={{ marginTop: "2rem" }}
      >
        <div className="dashboard-panel__heading">
          <div>
            <p className="panel-kicker">Today's Schedule</p>
            <h2>Upcoming Appointments</h2>
          </div>
        </div>
        <div className="dashboard-table-wrap">
          <table className="dashboard-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Service</th>
                <th>Time</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {todaysAppointments.length > 0 ? (
                todaysAppointments.map((apt) => (
                  <tr key={apt.id}>
                    <td>
                      <strong>{apt.user_name}</strong>
                    </td>
                    <td>{apt.service_name}</td>
                    <td>
                      {new Date(apt.appointment_start).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td>
                      <span
                        className={`dashboard-status dashboard-status--${apt.status}`}
                      >
                        {apt.status.replace("_", " ")}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={4}
                    style={{ textAlign: "center", padding: "1rem" }}
                  >
                    No appointments scheduled for today.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      <ProviderCalendarWidget />
    </section>
  );
}
