import React from "react";

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

type Props = {
  overview: Overview;
};

export default function DashboardStatsGrid({ overview }: Props) {
  const statusCount = (status: string) =>
    overview.appointments_by_status.find(
      (item) => item.status.toLowerCase() === status,
    )?.count ?? 0;

  return (
    <div className="dashboard-stat-grid">
      <article className="dashboard-stat dashboard-stat--accent">
        <span>Total bookings</span>
        <strong>{overview.total_appointments}</strong>
        <small>{overview.appointments_today} scheduled today</small>
      </article>

      <article className="dashboard-stat dashboard-stat--upcoming">
        <span>Upcoming appointments</span>
        <strong>{overview.upcoming_appointments}</strong>
        <small>Confirmed future appointments</small>
      </article>

      <article className="dashboard-stat dashboard-stat--completed">
        <span>Completed</span>
        <strong>{statusCount("completed")}</strong>
        <small>Completed appointments</small>
      </article>

      <article className="dashboard-stat dashboard-stat--cancelled">
        <span>Cancelled</span>
        <strong>{statusCount("cancelled")}</strong>
        <small>Cancelled appointments</small>
      </article>

      <article className="dashboard-stat dashboard-stat--providers">
        <span>Total providers</span>
        <strong>{overview.total_providers}</strong>
        <small>{overview.active_providers} active providers</small>
      </article>

      <article className="dashboard-stat dashboard-stat--services">
        <span>Total services</span>
        <strong>{overview.total_services}</strong>
        <small>{overview.active_services} active services</small>
      </article>
    </div>
  );
}
