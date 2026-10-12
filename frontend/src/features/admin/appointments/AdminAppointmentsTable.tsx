import { type AdminAppointment } from "../../../lib/adminAppointments";
import DataTable, { type ColumnDef } from "../../../components/common/DataTable";
import StatusBadge from "../../../components/common/StatusBadge";
import { formatDateTime } from "../../../utils/dateUtils";

type Props = {
  appointments: AdminAppointment[];
};

export function formatAppointmentDate(dateString: string): string {
  return formatDateTime(dateString);
}

export function getStatusClass(status: string): string {
  return `admin-appointment-status admin-appointment-status--${status.toLowerCase()}`;
}

const columns: ColumnDef<AdminAppointment>[] = [
  {
    header: "Customer",
    key: "customer",
    render: (apt) => (
      <div>
        <strong>{apt.user_name}</strong>
        <span style={{ display: "block", fontSize: "0.85rem", color: "#64748b" }}>
          {apt.user_email}
        </span>
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
    header: "Appointment time",
    key: "appointment_start",
    render: (apt) => formatDateTime(apt.appointment_start),
  },
  {
    header: "Duration",
    key: "duration_minutes",
    render: (apt) => `${apt.duration_minutes} min`,
  },
  {
    header: "Status",
    key: "status",
    render: (apt) => <StatusBadge status={apt.status} />,
  },
];

export default function AdminAppointmentsTable({ appointments }: Props) {
  return (
    <DataTable
      columns={columns}
      data={appointments}
      keyExtractor={(apt) => apt.id}
      wrapperClassName="admin-appointments-table-wrapper"
      tableClassName="admin-appointments-table"
      emptyMessage="No appointments found."
    />
  );
}
