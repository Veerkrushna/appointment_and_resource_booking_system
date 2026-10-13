import DataTable, { type ColumnDef } from "../../../components/common/DataTable";
import { formatDateTime } from "../../../utils/dateUtils";

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

const activityColumns: ColumnDef<AdminAppointment>[] = [
  {
    header: "Customer",
    key: "customer",
    render: (apt) => (
      <div>
        <strong>{apt.user_name}</strong>
        <small style={{ display: "block" }}>{apt.user_email}</small>
      </div>
    ),
  },
  {
    header: "Service",
    key: "service_name",
    accessor: "service_name",
  },
  {
    header: "Provider",
    key: "provider_name",
    accessor: "provider_name",
  },
  {
    header: "When",
    key: "appointment_start",
    render: (apt) => formatDateTime(apt.appointment_start),
  },
  {
    header: "Status",
    key: "status",
    render: (apt) => (
      <span className={`dashboard-status dashboard-status--${apt.status}`}>
        {apt.status}
      </span>
    ),
  },
];

export default function DashboardActivityTable({ appointments }: Props) {
  return (
    <section className="dashboard-panel dashboard-panel--table">
      <div className="dashboard-panel__heading">
        <div>
          <p className="panel-kicker">Latest activity</p>
          <h2>Appointments this month</h2>
        </div>
        <span className="dashboard-total">{appointments.length} bookings</span>
      </div>
      <DataTable
        columns={activityColumns}
        data={appointments.slice(0, 8)}
        keyExtractor={(apt) => apt.id}
        wrapperClassName="dashboard-table-wrap"
        tableClassName="dashboard-table"
        emptyMessage="No appointments have been recorded for this month."
      />
    </section>
  );
}
