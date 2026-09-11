import { useMemo, useState } from "react";
import type { FormEvent } from "react";

type Appointment = {
  id: string;
  service_id: string;
  provider_id: string;
  appointment_start: string;
  appointment_end: string;
  duration_minutes: number;
  status: string;
  notes: string | null;
};

type NamedRecord = { id: string; name: string };
type Tab = "upcoming" | "past" | "cancelled";

const tabs: { id: Tab; label: string }[] = [
  { id: "upcoming", label: "Upcoming" },
  { id: "past", label: "Past" },
  { id: "cancelled", label: "Cancelled" },
];

const userTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function toDateTimeLocal(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

async function getMessage(response: Response, fallback: string) {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

function AppointmentsPage() {
  const [email, setEmail] = useState(() => localStorage.getItem("appointment-email") || "");
  const [currentTime] = useState(() => Date.now());
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [services, setServices] = useState<Record<string, string>>({});
  const [providers, setProviders] = useState<Record<string, string>>({});
  const [selectedTab, setSelectedTab] = useState<Tab>("upcoming");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [reschedulingId, setReschedulingId] = useState<string | null>(null);
  const [rescheduleDate, setRescheduleDate] = useState("");

  async function loadAppointments(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const normalizedEmail = email.trim();
    if (!normalizedEmail) {
      setError("Enter the email address used when booking.");
      return;
    }

    localStorage.setItem("appointment-email", normalizedEmail);
    setIsLoading(true);
    setError(null);
    setActionError(null);

    try {
      const [appointmentsResponse, servicesResponse, providersResponse] = await Promise.all([
        fetch(`/api/appointments?user_email=${encodeURIComponent(normalizedEmail)}&timezone=${encodeURIComponent(userTimeZone)}`),
        fetch("/api/services"),
        fetch("/api/providers"),
      ]);
      if (!appointmentsResponse.ok) {
        throw new Error(await getMessage(appointmentsResponse, "Unable to load appointments."));
      }

      setAppointments(await appointmentsResponse.json());
      if (servicesResponse.ok) {
        const data: NamedRecord[] = await servicesResponse.json();
        setServices(Object.fromEntries(data.map((item) => [item.id, item.name])));
      }
      if (providersResponse.ok) {
        const data: NamedRecord[] = await providersResponse.json();
        setProviders(Object.fromEntries(data.map((item) => [item.id, item.name])));
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load appointments.");
    } finally {
      setIsLoading(false);
    }
  }

  const groupedAppointments = useMemo(() => {
    return {
      upcoming: appointments.filter((appointment) => appointment.status !== "cancelled" && new Date(appointment.appointment_end).getTime() >= currentTime),
      past: appointments.filter((appointment) => appointment.status === "completed" || (appointment.status !== "cancelled" && new Date(appointment.appointment_end).getTime() < currentTime)),
      cancelled: appointments.filter((appointment) => appointment.status === "cancelled"),
    };
  }, [appointments, currentTime]);

  async function cancelAppointment(id: string) {
    if (!window.confirm("Cancel this appointment?")) return;
    setActiveAction(id);
    setActionError(null);
    try {
      const response = await fetch(`/api/appointments/${id}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cancelled_by: "customer", reason: "Cancelled by customer" }),
      });
      if (!response.ok) throw new Error(await getMessage(response, "Unable to cancel this appointment."));
      await loadAppointments();
      setSelectedTab("cancelled");
    } catch (requestError) {
      setActionError(requestError instanceof Error ? requestError.message : "Unable to cancel this appointment.");
    } finally {
      setActiveAction(null);
    }
  }

  async function rescheduleAppointment(event: FormEvent<HTMLFormElement>, id: string) {
    event.preventDefault();
    if (!rescheduleDate) return;
    setActiveAction(id);
    setActionError(null);
    try {
      const response = await fetch(`/api/appointments/${id}?timezone=${encodeURIComponent(userTimeZone)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ appointment_start: new Date(rescheduleDate).toISOString() }),
      });
      if (!response.ok) throw new Error(await getMessage(response, "Unable to reschedule this appointment."));
      setReschedulingId(null);
      await loadAppointments();
    } catch (requestError) {
      setActionError(requestError instanceof Error ? requestError.message : "Unable to reschedule this appointment.");
    } finally {
      setActiveAction(null);
    }
  }

  const visibleAppointments = groupedAppointments[selectedTab];

  return (
    <section className="appointments-page">
      <div className="services-heading appointments-heading">
        <div>
          <p className="eyebrow">Your schedule, at a glance</p>
          <h1>My appointments</h1>
          <p className="services-intro">Keep track of what is next, revisit past visits, and make changes when plans shift.</p>
        </div>
        {!isLoading && <p className="service-count"><strong>{appointments.length}</strong> total {appointments.length === 1 ? "appointment" : "appointments"}</p>}
      </div>

      <form className="appointment-lookup" onSubmit={loadAppointments}>
        <label className="field-label" htmlFor="appointment-email">Booking email<span>Use the email address attached to your appointments.</span></label>
        <div className="appointment-lookup__controls"><input id="appointment-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /><button className="primary-button" type="submit" disabled={isLoading}>{isLoading ? "Loading..." : "Find appointments"}</button></div>
      </form>

      {error && <div className="status-message status-message--error" role="alert"><strong>We could not load your appointments.</strong><span>{error}</span></div>}
      {actionError && <div className="status-message status-message--error" role="alert"><span>{actionError}</span></div>}

      {!isLoading && !error && email && (
        <>
          <div className="appointment-tabs" role="tablist" aria-label="Appointment history">
            {tabs.map((tab) => <button className={selectedTab === tab.id ? "filter-button active" : "filter-button"} key={tab.id} type="button" role="tab" aria-selected={selectedTab === tab.id} onClick={() => setSelectedTab(tab.id)}>{tab.label} <span>{groupedAppointments[tab.id].length}</span></button>)}
          </div>

          {visibleAppointments.length > 0 ? <div className="appointment-list">
            {visibleAppointments.map((appointment) => {
              const isBusy = activeAction === appointment.id;
              const isCancelled = appointment.status === "cancelled";
              return <article className="appointment-card" key={appointment.id}>
                <div className="appointment-card__date"><span>{formatDate(appointment.appointment_start)}</span><strong>{formatTime(appointment.appointment_start)}</strong><small>{appointment.duration_minutes} min</small></div>
                <div className="appointment-card__details"><div className="appointment-card__topline"><span className={`appointment-status appointment-status--${appointment.status}`}>{appointment.status}</span></div><h2>{services[appointment.service_id] || "Booked service"}</h2><p>with {providers[appointment.provider_id] || "your provider"}</p>
                  {reschedulingId === appointment.id && <form className="reschedule-form" onSubmit={(event) => rescheduleAppointment(event, appointment.id)}><label className="field-label" htmlFor={`reschedule-${appointment.id}`}>New date and time<input id={`reschedule-${appointment.id}`} type="datetime-local" required value={rescheduleDate} onChange={(event) => setRescheduleDate(event.target.value)} /></label><div className="appointment-actions"><button className="primary-button" type="submit" disabled={isBusy}>{isBusy ? "Saving..." : "Save new time"}</button><button className="secondary-button" type="button" onClick={() => setReschedulingId(null)}>Keep current time</button></div></form>}
                </div>
                {!isCancelled && selectedTab === "upcoming" && reschedulingId !== appointment.id && <div className="appointment-actions"><button className="secondary-button" type="button" disabled={isBusy} onClick={() => { setReschedulingId(appointment.id); setRescheduleDate(toDateTimeLocal(appointment.appointment_start)); }}>Reschedule</button><button className="text-button" type="button" disabled={isBusy} onClick={() => void cancelAppointment(appointment.id)}>Cancel appointment</button></div>}
              </article>;
            })}
          </div> : <div className="empty-services appointment-empty"><span className="empty-services__mark" aria-hidden="true">+</span><h2>No {selectedTab} appointments</h2><p>{selectedTab === "upcoming" ? "Your next appointment will appear here once it is booked." : "There is nothing to show in this part of your history yet."}</p></div>}
        </>
      )}
    </section>
  );
}

export default AppointmentsPage;
