import { useEffect, useMemo, useState } from "react";

type Provider = {
  id: string;
  name: string;
  type: string;
  availability_status: string;
};

type Appointment = {
  id: string;
  service_id: string;
  user_name: string;
  user_email: string;
  appointment_start: string;
  appointment_end: string;
  duration_minutes: number;
  status: string;
};

type Service = { id: string; name: string };

function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function formatMonth(value: Date) {
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(value);
}

function formatSelectedDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function getCalendarDays(month: Date) {
  const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = new Date(firstDay);
  start.setDate(firstDay.getDate() - firstDay.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    return day;
  });
}

async function responseMessage(response: Response, fallback: string) {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [services, setServices] = useState<Record<string, string>>({});
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [month, setMonth] = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState(() => dateKey(new Date()));
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDirectory() {
      try {
        const [providersResponse, servicesResponse] = await Promise.all([fetch("/api/providers"), fetch("/api/services")]);
        if (!providersResponse.ok) throw new Error(await responseMessage(providersResponse, "Unable to load providers."));
        const providerData: Provider[] = await providersResponse.json();
        setProviders(providerData);
        setSelectedProviderId(providerData[0]?.id || "");
        if (servicesResponse.ok) {
          const serviceData: Service[] = await servicesResponse.json();
          setServices(Object.fromEntries(serviceData.map((service) => [service.id, service.name])));
        }
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Unable to load providers.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadDirectory();
  }, []);

  useEffect(() => {
    if (!selectedProviderId) return;
    async function loadAppointments() {
      setError(null);
      try {
        const response = await fetch(`/api/appointments?provider_id=${selectedProviderId}`);
        if (!response.ok) throw new Error(await responseMessage(response, "Unable to load provider bookings."));
        setAppointments(await response.json());
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Unable to load provider bookings.");
      }
    }

    void loadAppointments();
  }, [selectedProviderId]);

  const calendarDays = useMemo(() => getCalendarDays(month), [month]);
  const appointmentsByDay = useMemo(() => {
    const grouped: Record<string, Appointment[]> = {};
    appointments.forEach((appointment) => {
      const key = dateKey(new Date(appointment.appointment_start));
      grouped[key] = [...(grouped[key] || []), appointment];
    });
    return grouped;
  }, [appointments]);
  const selectedAppointments = appointmentsByDay[selectedDate] || [];
  const selectedProvider = providers.find((provider) => provider.id === selectedProviderId);

  function moveMonth(amount: number) {
    setMonth((current) => new Date(current.getFullYear(), current.getMonth() + amount, 1));
  }

  return (
    <section className="provider-calendar-page">
      <div className="services-heading provider-calendar-heading">
        <div>
          <p className="eyebrow">Operations view</p>
          <h1>Provider schedule</h1>
          <p className="services-intro">Review bookings by provider, spot busy days, and open the day agenda for the full appointment detail.</p>
        </div>
        {!isLoading && <p className="service-count"><strong>{appointments.filter((appointment) => appointment.status !== "cancelled").length}</strong> active bookings</p>}
      </div>

      {error && <div className="status-message status-message--error" role="alert"><strong>We could not load the schedule.</strong><span>{error}</span></div>}

      <div className="provider-calendar-toolbar">
        <label className="field-label" htmlFor="provider-select">Provider<span>Select a provider to view their bookings.</span></label>
        <select id="provider-select" value={selectedProviderId} onChange={(event) => setSelectedProviderId(event.target.value)} disabled={isLoading}>
          {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
        </select>
        {selectedProvider && <span className={`provider-availability provider-availability--${selectedProvider.availability_status}`}>{selectedProvider.availability_status.replace("_", " ")}</span>}
      </div>

      {!isLoading && !error && selectedProviderId && <div className="provider-calendar-layout">
        <div className="provider-calendar-panel">
          <div className="calendar-header"><button className="calendar-nav" type="button" aria-label="Previous month" onClick={() => moveMonth(-1)}>&#8592;</button><h2>{formatMonth(month)}</h2><button className="calendar-nav" type="button" aria-label="Next month" onClick={() => moveMonth(1)}>&#8594;</button></div>
          <div className="calendar-weekdays" aria-hidden="true">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <span key={day}>{day}</span>)}</div>
          <div className="calendar-grid" role="grid" aria-label={`${formatMonth(month)} provider schedule`}>
            {calendarDays.map((day) => {
              const key = dateKey(day);
              const dayAppointments = appointmentsByDay[key] || [];
              const isCurrentMonth = day.getMonth() === month.getMonth();
              const isSelected = key === selectedDate;
              return <button className={`calendar-day${isCurrentMonth ? "" : " calendar-day--outside"}${isSelected ? " calendar-day--selected" : ""}`} key={key} type="button" role="gridcell" aria-label={`${formatSelectedDate(key)}, ${dayAppointments.length} bookings`} onClick={() => setSelectedDate(key)}><span>{day.getDate()}</span>{dayAppointments.length > 0 && <small className="calendar-day__count">{dayAppointments.length}</small>}<div className="calendar-day__dots">{dayAppointments.slice(0, 3).map((appointment) => <i className={`calendar-dot calendar-dot--${appointment.status}`} key={appointment.id} />)}</div></button>;
            })}
          </div>
        </div>

        <aside className="provider-agenda">
          <p className="panel-kicker">Day agenda</p>
          <h2>{formatSelectedDate(selectedDate)}</h2>
          {selectedAppointments.length > 0 ? <div className="provider-agenda__list">{selectedAppointments.map((appointment) => <article className={`provider-booking provider-booking--${appointment.status}`} key={appointment.id}><div><strong>{formatTime(appointment.appointment_start)}</strong><span>{appointment.duration_minutes} min</span></div><section><h3>{services[appointment.service_id] || "Booked service"}</h3><p>{appointment.user_name}</p><small>{appointment.user_email}</small></section><em>{appointment.status}</em></article>)}</div> : <div className="provider-agenda__empty"><span aria-hidden="true">+</span><p>No bookings for this day.</p><small>Choose another date to inspect the schedule.</small></div>}
        </aside>
      </div>}

      {!isLoading && !error && providers.length === 0 && <div className="empty-services"><span className="empty-services__mark" aria-hidden="true">+</span><h2>No providers available</h2><p>Add a provider to start viewing schedules.</p></div>}
    </section>
  );
}

export default ProvidersPage;
