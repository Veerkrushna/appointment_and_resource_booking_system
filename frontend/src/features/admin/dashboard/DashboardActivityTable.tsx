import React from "react";

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

type Props = {
  appointments: AdminAppointment[];
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function DashboardActivityTable({ appointments }: Props) {
  return (
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
  );
}
