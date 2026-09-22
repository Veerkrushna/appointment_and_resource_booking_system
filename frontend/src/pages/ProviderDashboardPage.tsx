import { useState, useEffect } from "react";
import { useAuth } from "../auth/useAuth";

// Mock data types
type Appointment = {
  id: string;
  customerName: string;
  service: string;
  time: string;
  status: "upcoming" | "completed" | "cancelled";
};

export default function ProviderDashboardPage() {
  const { customer } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  
  // Mock statistics
  const stats = {
    today: 5,
    upcoming: 12,
    completed: 45,
    remainingToday: 2,
  };

  const mockAppointments: Appointment[] = [
    { id: "1", customerName: "Alice Smith", service: "Massage Therapy", time: "10:00 AM", status: "completed" },
    { id: "2", customerName: "John Doe", service: "Consultation", time: "1:00 PM", status: "upcoming" },
    { id: "3", customerName: "Emma Johnson", service: "Follow-up", time: "3:30 PM", status: "upcoming" },
  ];

  useEffect(() => {
    setIsLoading(false);
  }, []);

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
          <p className="services-intro">Here is an overview of your schedule and appointments.</p>
        </div>
      </header>

      <div className="dashboard-stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
        <article className="dashboard-stat dashboard-stat--warm">
          <span>Today's Appointments</span>
          <strong>{stats.today}</strong>
          <small>Total scheduled today</small>
        </article>
        <article className="dashboard-stat dashboard-stat--warm">
          <span>Remaining Today</span>
          <strong>{stats.remainingToday}</strong>
          <small>Appointments left</small>
        </article>
        <article className="dashboard-stat dashboard-stat--warm">
          <span>Upcoming Appointments</span>
          <strong>{stats.upcoming}</strong>
          <small>In the next 7 days</small>
        </article>
        <article className="dashboard-stat dashboard-stat--warm">
          <span>Completed</span>
          <strong>{stats.completed}</strong>
          <small>Total completed</small>
        </article>
      </div>

      <section className="dashboard-panel dashboard-panel--table" style={{ marginTop: '2rem' }}>
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
              {mockAppointments.map((apt) => (
                <tr key={apt.id}>
                  <td><strong>{apt.customerName}</strong></td>
                  <td>{apt.service}</td>
                  <td>{apt.time}</td>
                  <td>
                    <span className={`dashboard-status dashboard-status--${apt.status}`}>
                      {apt.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
