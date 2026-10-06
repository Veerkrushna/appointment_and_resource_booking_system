
export type NamedRecord = {
  id: string;
  name: string;
};

type Props = {
  search: string;
  setSearch: (value: string) => void;
  providerId: string;
  setProviderId: (value: string) => void;
  serviceId: string;
  setServiceId: (value: string) => void;
  status: string;
  setStatus: (value: string) => void;
  startDate: string;
  setStartDate: (value: string) => void;
  endDate: string;
  setEndDate: (value: string) => void;
  providers: NamedRecord[];
  services: NamedRecord[];
};

export default function AdminAppointmentsFilters({
  search,
  setSearch,
  providerId,
  setProviderId,
  serviceId,
  setServiceId,
  status,
  setStatus,
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  providers,
  services,
}: Props) {
  return (
    <div className="admin-appointments-filters">
      <div className="admin-appointments-filter">
        <label htmlFor="appointment-search">Search customer</label>
        <input
          id="appointment-search"
          type="search"
          placeholder="Email or phone"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>

      <div className="admin-appointments-filter">
        <label htmlFor="appointment-provider">Provider</label>
        <select
          id="appointment-provider"
          value={providerId}
          onChange={(event) => setProviderId(event.target.value)}
        >
          <option value="">All providers</option>
          {providers.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.name}
            </option>
          ))}
        </select>
      </div>

      <div className="admin-appointments-filter">
        <label htmlFor="appointment-service">Service</label>
        <select
          id="appointment-service"
          value={serviceId}
          onChange={(event) => setServiceId(event.target.value)}
        >
          <option value="">All services</option>
          {services.map((service) => (
            <option key={service.id} value={service.id}>
              {service.name}
            </option>
          ))}
        </select>
      </div>

      <div className="admin-appointments-filter">
        <label htmlFor="appointment-status">Status</label>
        <select
          id="appointment-status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="">All statuses</option>
          <option value="confirmed">Confirmed</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      <div className="admin-appointments-filter">
        <label htmlFor="appointment-start-date">From</label>
        <input
          id="appointment-start-date"
          type="date"
          value={startDate}
          onChange={(event) => setStartDate(event.target.value)}
        />
      </div>

      <div className="admin-appointments-filter">
        <label htmlFor="appointment-end-date">To</label>
        <input
          id="appointment-end-date"
          type="date"
          value={endDate}
          onChange={(event) => setEndDate(event.target.value)}
        />
      </div>
    </div>
  );
}
