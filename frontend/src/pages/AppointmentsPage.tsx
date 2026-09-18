import { useCallback, useEffect, useMemo, useState } from "react";
import RescheduleFlow from "../components/RescheduleFlow";
import { useAuth } from "../auth/useAuth";
import {
  cancelCustomerAppointment,
  fetchCustomerAppointments,
  type CustomerAppointment,
  type NamedRecord,
} from "../lib/customerAppointments";
type Tab = "upcoming" | "past" | "cancelled";

const tabs: { id: Tab; label: string }[] = [
  { id: "upcoming", label: "Upcoming" },
  { id: "past", label: "Past" },
  { id: "cancelled", label: "Cancelled" },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatStatusLabel(value: string) {
  const labels: Record<string, string> = {
    pending: "Pending",
    confirmed: "Confirmed",
    completed: "Completed",
    cancelled: "Cancelled",
  };

  return labels[value] ?? value;
}

function AppointmentsPage() {
  const { token } = useAuth();
  const [currentTime] = useState(() => Date.now());
  const [appointments, setAppointments] = useState<CustomerAppointment[]>([]);
  const [services, setServices] = useState<Record<string, string>>({});
  const [providers, setProviders] = useState<Record<string, string>>({});
  const [selectedTab, setSelectedTab] = useState<Tab>("upcoming");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [rescheduling, setRescheduling] = useState<CustomerAppointment | null>(
    null,
  );

  const loadAppointments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setActionError(null);

    try {
      const firstPage = await fetchCustomerAppointments(token!);

      const remainingPages = await Promise.all(
        Array.from({ length: firstPage.total_pages - 1 }, (_, index) =>
          fetchCustomerAppointments(token!, index + 2),
        ),
      );

      const allAppointments = [
        ...firstPage.appointments,
        ...remainingPages.flatMap((page) => page.appointments),
      ];

      const [servicesResponse, providersResponse] = await Promise.all([
        fetch("/api/services"),
        fetch("/api/providers"),
      ]);

      setAppointments(allAppointments);
      if (servicesResponse.ok) {
        const data: NamedRecord[] = await servicesResponse.json();
        setServices(
          Object.fromEntries(data.map((item) => [item.id, item.name])),
        );
      }
      if (providersResponse.ok) {
        const data: NamedRecord[] = await providersResponse.json();
        setProviders(
          Object.fromEntries(data.map((item) => [item.id, item.name])),
        );
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load appointments.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadAppointments(), 0);
    return () => window.clearTimeout(timer);
  }, [loadAppointments]);

  const groupedAppointments = useMemo(() => {
    return {
      upcoming: appointments.filter(
        (appointment) =>
          ["pending", "confirmed"].includes(appointment.status) &&
          new Date(appointment.appointment_end).getTime() >= currentTime,
      ),
      past: appointments.filter(
        (appointment) =>
          appointment.status === "completed" ||
          (["pending", "confirmed"].includes(appointment.status) &&
            new Date(appointment.appointment_end).getTime() < currentTime),
      ),
      cancelled: appointments.filter(
        (appointment) => appointment.status === "cancelled",
      ),
    };
  }, [appointments, currentTime]);

  async function cancelAppointment(id: string) {
    if (!window.confirm("Cancel this appointment?")) return;
    setActiveAction(id);
    setActionError(null);
    try {
      await cancelCustomerAppointment(token!, id);
      await loadAppointments();
      setSelectedTab("cancelled");
    } catch (requestError) {
      setActionError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to cancel this appointment.",
      );
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
          <p className="services-intro">
            Keep track of what is next, revisit past visits, and make changes
            when plans shift.
          </p>
        </div>
        {!isLoading && (
          <p className="service-count">
            <strong>{appointments.length}</strong> total{" "}
            {appointments.length === 1 ? "appointment" : "appointments"}
          </p>
        )}
      </div>

      {error && (
        <div className="status-message status-message--error" role="alert">
          <strong>We could not load your appointments.</strong>
          <span>{error}</span>
        </div>
      )}
      {actionError && (
        <div className="status-message status-message--error" role="alert">
          <span>{actionError}</span>
        </div>
      )}

      {!isLoading && !error && (
        <>
          <div
            className="appointment-tabs"
            role="tablist"
            aria-label="Appointment history"
          >
            {tabs.map((tab) => (
              <button
                className={
                  selectedTab === tab.id
                    ? "filter-button active"
                    : "filter-button"
                }
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={selectedTab === tab.id}
                onClick={() => setSelectedTab(tab.id)}
              >
                {tab.label} <span>{groupedAppointments[tab.id].length}</span>
              </button>
            ))}
          </div>

          {visibleAppointments.length > 0 ? (
            <div className="appointment-list">
              {visibleAppointments.map((appointment) => {
                const isBusy = activeAction === appointment.id;
                const canChange = selectedTab === "upcoming" && !isBusy;
                return (
                  <article className="appointment-card" key={appointment.id}>
                    <div className="appointment-card__date">
                      <span>{formatDate(appointment.appointment_start)}</span>
                      <strong>
                        {formatTime(appointment.appointment_start)}
                      </strong>
                      <small>{appointment.duration_minutes} min</small>
                    </div>
                    <div className="appointment-card__details">
                      <div className="appointment-card__topline">
                        <span
                          className={`appointment-status appointment-status--${appointment.status}`}
                        >
                          {formatStatusLabel(appointment.status)}
                        </span>
                      </div>
                      <h2>
                        {services[appointment.service_id] || "Booked service"}
                      </h2>
                      <p>
                        with{" "}
                        {providers[appointment.provider_id] || "your provider"}
                      </p>
                      {appointment.notes && (
                        <div className="appointment-detail">
                          <span>Note: {appointment.notes}</span>
                        </div>
                      )}
                      {rescheduling?.id === appointment.id && (
                        <RescheduleFlow
                          appointment={appointment}
                          serviceName={
                            services[appointment.service_id] || "Booked service"
                          }
                          providerName={
                            providers[appointment.provider_id] ||
                            "Your provider"
                          }
                          token={token!}
                          onCancel={() => setRescheduling(null)}
                          onComplete={async () => {
                            setRescheduling(null);
                            await loadAppointments();
                          }}
                        />
                      )}
                    </div>
                    <div className="appointment-actions">
                      {canChange && (
                        <>
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => setRescheduling(appointment)}
                          >
                            Reschedule
                          </button>
                          <button
                            className="text-button"
                            type="button"
                            onClick={() =>
                              void cancelAppointment(appointment.id)
                            }
                          >
                            Cancel appointment
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="empty-services appointment-empty">
              <span className="empty-services__mark" aria-hidden="true">
                +
              </span>
              <h2>No {selectedTab} appointments</h2>
              <p>
                {selectedTab === "upcoming"
                  ? "Your next appointment will appear here once it is booked."
                  : "There is nothing to show in this part of your history yet."}
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default AppointmentsPage;
