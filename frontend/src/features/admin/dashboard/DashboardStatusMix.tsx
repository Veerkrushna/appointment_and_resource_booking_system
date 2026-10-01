import React from "react";

type Overview = {
  total_appointments: number;
  appointments_by_status: { status: string; count: number }[];
  [key: string]: any;
};

type Props = {
  overview: Overview;
};

export default function DashboardStatusMix({ overview }: Props) {
  return (
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
  );
}
