import React from "react";
import { type AdminAppointment } from "../../../lib/adminAppointments";

type Props = {
  appointments: AdminAppointment[];
};

export function formatAppointmentDate(dateString: string): string {
  return new Date(dateString).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function getStatusClass(status: string): string {
  return `admin-appointment-status admin-appointment-status--${status.toLowerCase()}`;
}

export default function AdminAppointmentsTable({ appointments }: Props) {
  if (appointments.length === 0) {
    return <p>No appointments found.</p>;
  }

  return (
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
              <td>{formatAppointmentDate(appointment.appointment_start)}</td>
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
  );
}
