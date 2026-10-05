import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppointmentReview from "../components/AppointmentReview";
import RescheduleFlow from "../components/RescheduleFlow";
import { useAuth } from "../auth/useAuth";
import {
  cancelCustomerAppointment,
  fetchCustomerAppointments,
  type CustomerAppointment,
  type NamedRecord,
} from "../lib/customerAppointments";
import {
  cancelAppointmentSeries,
  AppointmentSeriesCancellationError,
  fetchAppointmentSeries,
  type AppointmentSeriesDetail,
} from "../lib/appointmentSeries";
type Tab = "upcoming" | "past" | "cancelled";

const tabs: { id: Tab; label: string }[] = [
  { id: "upcoming", label: "Upcoming" },
  { id: "past", label: "Past" },
  { id: "cancelled", label: "Cancelled" },
];

type AppointmentDisplayGroup = {
  key: string;
  seriesId: string | null;
  appointments: CustomerAppointment[];
};

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
    confirmed: "Confirmed",
    completed: "Completed",
    cancelled: "Cancelled",
    in_progress: "In progress",
  };

  return labels[value] ?? value;
}

function formatSeriesRule(series: AppointmentSeriesDetail) {
  const unit = series.frequency === "monthly" ? "month" : "week";
  const frequency =
    series.interval === 1
      ? series.frequency === "monthly"
        ? "Monthly"
        : "Weekly"
      : `Every ${series.interval} ${unit}s`;
  const ending =
    series.end_mode === "count"
      ? `After ${formatSeriesOccurrenceCount(series)}`
      : series.end_date
        ? `Through ${formatDate(series.end_date)}`
        : "End date unavailable";

  return `${frequency}; ${ending}`;
}

function formatSeriesOccurrenceCount(series: AppointmentSeriesDetail) {
  const count = series.occurrence_count ?? series.occurrences.length;
  return `${count} ${count === 1 ? "occurrence" : "occurrences"}`;
}

function AppointmentsPage() {
  const { customer, token, isLoading: authIsLoading } = useAuth();
  const [currentTime, setCurrentTime] = useState(() => Date.now());
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
  const [expandedSeriesIds, setExpandedSeriesIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [seriesDetails, setSeriesDetails] = useState<
    Record<string, AppointmentSeriesDetail>
  >({});
  const [seriesLoading, setSeriesLoading] = useState<Record<string, boolean>>(
    {},
  );
  const [seriesErrors, setSeriesErrors] = useState<Record<string, string>>({});
  const [seriesCancellationLoading, setSeriesCancellationLoading] = useState<
    Record<string, boolean>
  >({});
  const [seriesCancellationErrors, setSeriesCancellationErrors] = useState<
    Record<string, string>
  >({});
  const seriesDetailCache = useRef(new Map<string, AppointmentSeriesDetail>());
  const seriesRequests = useRef(new Map<string, Promise<void>>());
  const seriesCancellationRequests = useRef(new Map<string, Promise<void>>());
  const canLoadSeriesDetails =
    !authIsLoading &&
    Boolean(token) &&
    customer?.role.toLowerCase() === "customer";
  const canCancelSeries =
    !authIsLoading &&
    Boolean(token) &&
    customer?.role?.toLowerCase() === "customer";

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

  useEffect(() => {
    const timer = window.setInterval(() => setCurrentTime(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const canModify = useCallback(
    (appointment: CustomerAppointment) => {
      if (appointment.status !== "confirmed") return false;
      return (
        new Date(appointment.appointment_start).getTime() - 2 * 60 * 60 * 1000 >
        currentTime
      );
    },
    [currentTime],
  );

  const groupedAppointments = useMemo(() => {
    return {
      upcoming: appointments.filter(
        (appointment) =>
          ["confirmed", "in_progress"].includes(appointment.status) &&
          new Date(appointment.appointment_end).getTime() >= currentTime,
      ),
      past: appointments.filter(
        (appointment) =>
          appointment.status === "completed" ||
          (["confirmed"].includes(appointment.status) &&
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

  function markSeriesCancelled(seriesId: string) {
    const cachedSeries = seriesDetailCache.current.get(seriesId);
    if (!cachedSeries) return;

    const cancelledSeries = { ...cachedSeries, status: "cancelled" as const };
    seriesDetailCache.current.set(seriesId, cancelledSeries);
    setSeriesDetails((current) => ({
      ...current,
      [seriesId]: cancelledSeries,
    }));
  }

  function cancelSeries(seriesId: string) {
    if (
      !canCancelSeries ||
      !token ||
      seriesCancellationRequests.current.has(seriesId)
    ) {
      return Promise.resolve();
    }
    if (
      !window.confirm(
        "Cancel this entire series? Future confirmed appointments will be cancelled.",
      )
    ) {
      return Promise.resolve();
    }

    setSeriesCancellationLoading((current) => ({
      ...current,
      [seriesId]: true,
    }));
    setSeriesCancellationErrors((current) => {
      const next = { ...current };
      delete next[seriesId];
      return next;
    });

    const request = cancelAppointmentSeries(token, seriesId)
      .then((result) => {
        const cancelledIds = new Set(result.cancelled_appointment_ids);
        setAppointments((current) =>
          current.map((appointment) =>
            cancelledIds.has(appointment.id)
              ? { ...appointment, status: "cancelled" }
              : appointment,
          ),
        );
        markSeriesCancelled(seriesId);
      })
      .catch((requestError: unknown) => {
        if (
          requestError instanceof AppointmentSeriesCancellationError &&
          requestError.status === 409
        ) {
          markSeriesCancelled(seriesId);
        }
        setSeriesCancellationErrors((current) => ({
          ...current,
          [seriesId]:
            requestError instanceof Error
              ? requestError.message
              : "Unable to cancel this series. Please try again.",
        }));
      })
      .finally(() => {
        seriesCancellationRequests.current.delete(seriesId);
        setSeriesCancellationLoading((current) => ({
          ...current,
          [seriesId]: false,
        }));
      });

    seriesCancellationRequests.current.set(seriesId, request);
    return request;
  }

  const visibleAppointments = groupedAppointments[selectedTab];

  const visibleAppointmentGroups = useMemo(() => {
    const groups: AppointmentDisplayGroup[] = [];
    const recurringGroups = new Map<string, AppointmentDisplayGroup>();

    for (const appointment of visibleAppointments) {
      if (!appointment.series_id) {
        groups.push({
          key: appointment.id,
          seriesId: null,
          appointments: [appointment],
        });
        continue;
      }

      const existingGroup = recurringGroups.get(appointment.series_id);
      if (existingGroup) {
        existingGroup.appointments.push(appointment);
      } else {
        const group = {
          key: `series-${appointment.series_id}`,
          seriesId: appointment.series_id,
          appointments: [appointment],
        };
        recurringGroups.set(appointment.series_id, group);
        groups.push(group);
      }
    }

    return groups;
  }, [visibleAppointments]);

  function loadSeriesDetails(seriesId: string) {
    if (!canLoadSeriesDetails || !token) return Promise.resolve();
    if (seriesDetailCache.current.has(seriesId)) return Promise.resolve();

    const inFlight = seriesRequests.current.get(seriesId);
    if (inFlight) return inFlight;

    setSeriesLoading((current) => ({ ...current, [seriesId]: true }));
    setSeriesErrors((current) => {
      const next = { ...current };
      delete next[seriesId];
      return next;
    });

    const request = fetchAppointmentSeries(token, seriesId)
      .then((series) => {
        seriesDetailCache.current.set(seriesId, series);
        setSeriesDetails((current) => ({ ...current, [seriesId]: series }));
      })
      .catch((requestError) => {
        setSeriesErrors((current) => ({
          ...current,
          [seriesId]:
            requestError instanceof Error
              ? requestError.message
              : "Unable to load recurring series. Please try again.",
        }));
      })
      .finally(() => {
        seriesRequests.current.delete(seriesId);
        setSeriesLoading((current) => ({ ...current, [seriesId]: false }));
      });

    seriesRequests.current.set(seriesId, request);
    return request;
  }

  function toggleSeries(seriesId: string) {
    if (!canLoadSeriesDetails) return;

    const willExpand = !expandedSeriesIds.has(seriesId);
    setExpandedSeriesIds((current) => {
      const next = new Set(current);
      if (next.has(seriesId)) next.delete(seriesId);
      else next.add(seriesId);
      return next;
    });
    if (willExpand) void loadSeriesDetails(seriesId);
  }

  function renderAppointmentCard(appointment: CustomerAppointment) {
    const isBusy = activeAction === appointment.id;
    const canChange = selectedTab === "upcoming" && !isBusy;
    const isRecurring = Boolean(appointment.series_id);

    return (
      <article className="appointment-card" key={appointment.id}>
        <div className="appointment-card__date">
          <span>{formatDate(appointment.appointment_start)}</span>
          <strong>{formatTime(appointment.appointment_start)}</strong>
          <small>{appointment.duration_minutes} min</small>
        </div>
        <div className="appointment-card__details">
          <div
            className={`appointment-card__topline${isRecurring ? " appointment-card__topline--recurring" : ""}`}
          >
            <span
              className={`appointment-status appointment-status--${appointment.status}`}
            >
              {formatStatusLabel(appointment.status)}
            </span>
            {isRecurring && (
              <span className="appointment-series-badge">Recurring</span>
            )}
            {isRecurring &&
              typeof appointment.occurrence_number === "number" && (
                <span className="appointment-series-occurrence">
                  Occurrence {appointment.occurrence_number}
                </span>
              )}
          </div>
          <h2>{services[appointment.service_id] || "Booked service"}</h2>
          <p>with {providers[appointment.provider_id] || "your provider"}</p>

          {appointment.notes && (
            <div className="appointment-detail">
              <span>Note: {appointment.notes}</span>
            </div>
          )}

          {rescheduling?.id === appointment.id && (
            <RescheduleFlow
              appointment={appointment}
              serviceName={services[appointment.service_id] || "Booked service"}
              providerName={
                providers[appointment.provider_id] || "Your provider"
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
          {customer?.role.toLowerCase() === "customer" &&
            appointment.status.toLowerCase() === "completed" && (
              <AppointmentReview
                appointmentId={appointment.id}
                providerName={
                  providers[appointment.provider_id] || "Your provider"
                }
                serviceName={
                  services[appointment.service_id] || "Booked service"
                }
                token={token!}
              />
            )}
          {canChange && (
            <>
              <button
                className="secondary-button"
                type="button"
                disabled={!canModify(appointment)}
                title={
                  !canModify(appointment)
                    ? "Changes are not allowed within 2 hours of the booking."
                    : undefined
                }
                onClick={() => setRescheduling(appointment)}
              >
                Reschedule
              </button>
              <button
                className="text-button"
                type="button"
                disabled={!canModify(appointment)}
                title={
                  !canModify(appointment)
                    ? "Changes are not allowed within 2 hours of the booking."
                    : undefined
                }
                onClick={() => void cancelAppointment(appointment.id)}
              >
                Cancel appointment
              </button>
            </>
          )}
        </div>
      </article>
    );
  }

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

          {visibleAppointmentGroups.length > 0 ? (
            <div className="appointment-list">
              {visibleAppointmentGroups.map((group) =>
                group.seriesId === null ? (
                  renderAppointmentCard(group.appointments[0])
                ) : (
                  <section
                    className="appointment-series-group"
                    key={group.key}
                    aria-label="Recurring appointment series"
                  >
                    {canLoadSeriesDetails ? (
                      <button
                        className="appointment-series-group__toggle"
                        type="button"
                        aria-expanded={expandedSeriesIds.has(group.seriesId)}
                        aria-controls={`appointment-series-details-${group.seriesId}`}
                        onClick={() => toggleSeries(group.seriesId!)}
                      >
                        <span className="appointment-series-badge">Recurring</span>
                        <span className="appointment-series-group__summary">
                          {seriesDetails[group.seriesId]
                            ? formatSeriesRule(seriesDetails[group.seriesId])
                            : "Recurring appointment"}
                        </span>
                        {seriesDetails[group.seriesId] && (
                          <>
                            <span className="appointment-series-group__status">
                              {seriesDetails[group.seriesId].status === "active"
                                ? "Active"
                                : "Cancelled"}
                            </span>
                            <span className="appointment-series-group__count">
                              {formatSeriesOccurrenceCount(
                                seriesDetails[group.seriesId],
                              )}
                            </span>
                          </>
                        )}
                        <span className="appointment-series-group__action">
                          {expandedSeriesIds.has(group.seriesId)
                            ? "Hide details"
                            : "Show details"}
                        </span>
                      </button>
                    ) : (
                      <h2 className="appointment-series-group__heading">
                        <span className="appointment-series-badge">Recurring</span>
                        <span>Recurring appointment</span>
                      </h2>
                    )}
                    {canLoadSeriesDetails && (
                      <div
                        className="appointment-series-group__details"
                        id={`appointment-series-details-${group.seriesId}`}
                        hidden={!expandedSeriesIds.has(group.seriesId)}
                      >
                        {expandedSeriesIds.has(group.seriesId) && (
                          <>
                            {seriesLoading[group.seriesId] && (
                              <p className="status-message">
                                Loading recurring series details...
                              </p>
                            )}
                            {seriesErrors[group.seriesId] && (
                              <div
                                className="status-message status-message--error"
                                role="alert"
                              >
                                <span>{seriesErrors[group.seriesId]}</span>
                                <button
                                  className="text-button"
                                  type="button"
                                  disabled={seriesLoading[group.seriesId]}
                                  onClick={() =>
                                    void loadSeriesDetails(group.seriesId!)
                                  }
                                >
                                  Retry
                                </button>
                              </div>
                            )}
                            {seriesDetails[group.seriesId] && (
                              <dl className="appointment-series-group__metadata">
                                <div>
                                  <dt>Service</dt>
                                  <dd>
                                    {services[
                                      seriesDetails[group.seriesId].service_id
                                    ] || "Booked service"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Provider</dt>
                                  <dd>
                                    {providers[
                                      seriesDetails[group.seriesId].provider_id
                                    ] || "Your provider"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Starts</dt>
                                  <dd>
                                    {seriesDetails[group.seriesId].start_date} at{" "}
                                    {seriesDetails[
                                      group.seriesId
                                    ].local_start_time.slice(0, 5)}{" "}
                                    (
                                      {
                                        seriesDetails[group.seriesId]
                                          .provider_timezone
                                      }
                                    )
                                  </dd>
                                </div>
                              </dl>
                            )}
                            {canCancelSeries &&
                              seriesDetails[group.seriesId] &&
                              seriesDetails[group.seriesId].status !==
                                "cancelled" && (
                                <button
                                  className="text-button"
                                  type="button"
                                  disabled={
                                    seriesCancellationLoading[group.seriesId]
                                  }
                                  onClick={() =>
                                    void cancelSeries(group.seriesId!)
                                  }
                                >
                                  {seriesCancellationLoading[group.seriesId]
                                    ? "Cancelling series..."
                                    : "Cancel Series"}
                                </button>
                              )}
                            {seriesCancellationErrors[group.seriesId] && (
                              <p
                                className="appointment-series-cancel-error"
                                role="alert"
                              >
                                {seriesCancellationErrors[group.seriesId]}
                              </p>
                            )}
                          </>
                        )}
                      </div>
                    )}
                    <div className="appointment-series-group__occurrences">
                      {group.appointments.map(renderAppointmentCard)}
                    </div>
                  </section>
                ),
              )}
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
