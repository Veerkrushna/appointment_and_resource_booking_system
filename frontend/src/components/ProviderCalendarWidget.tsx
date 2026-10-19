import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/useAuth";
import {
  dateKey,
  formatTime,
  formatSelectedDate,
  getCalendarDays,
} from "../utils/dateUtils";

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

async function responseMessage(response: Response, fallback: string) {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export default function ProviderCalendarWidget() {
  const { customer, token } = useAuth();

  const [services, setServices] = useState<Record<string, string>>({});
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [month, setMonth] = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState(() => dateKey(new Date()));
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scheduleData, setScheduleData] = useState<any>(null);

  useEffect(() => {
    async function loadData() {
      if (!customer?.email) return;
      try {
        const providersResponse = await fetch("/api/providers");
        if (!providersResponse.ok)
          throw new Error(
            await responseMessage(
              providersResponse,
              "Unable to load providers.",
            ),
          );
        const providers = await providersResponse.json();
        const provider = providers.find((p: any) => p.email === customer.email);

        if (!provider) {
          setAppointments([]);
          setServices({});
          setIsLoading(false);
          return;
        }

        const [appointmentsResponse, servicesResponse, scheduleResponse] =
          await Promise.all([
            fetch(`/api/appointments?provider_id=${provider.id}`, {
              headers: token ? { Authorization: `Bearer ${token}` } : undefined,
            }),
            fetch("/api/services"),
            fetch(`/api/providers/${provider.id}/schedule`),
          ]);

        if (scheduleResponse.ok) {
          const schedule = await scheduleResponse.json();
          setScheduleData(schedule);
        }

        if (!appointmentsResponse.ok)
          throw new Error(
            await responseMessage(
              appointmentsResponse,
              "Unable to load bookings.",
            ),
          );
        const appointmentsData = await appointmentsResponse.json();
        setAppointments(appointmentsData.appointments || []);

        if (servicesResponse.ok) {
          const serviceData: Service[] = await servicesResponse.json();
          setServices(
            Object.fromEntries(
              serviceData.map((service) => [service.id, service.name]),
            ),
          );
        }
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load calendar data.",
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadData();
  }, [customer?.id, token]);

  const [calendarView, setCalendarView] = useState<"month" | "week">("month");
  const calendarDays = useMemo(
    () => getCalendarDays(month, calendarView),
    [month, calendarView],
  );
  const appointmentsByDay = useMemo(() => {
    const grouped: Record<string, Appointment[]> = {};
    appointments.forEach((appointment) => {
      const key = dateKey(new Date(appointment.appointment_start));
      grouped[key] = [...(grouped[key] || []), appointment];
    });
    return grouped;
  }, [appointments]);

  const selectedAppointments = appointmentsByDay[selectedDate] || [];

  function moveMonth(amount: number) {
    setMonth((current) => {
      const next = new Date(current);
      next.setDate(
        current.getDate() + (calendarView === "month" ? amount * 31 : amount * 7),
      );
      return next;
    });
  }

  function formatCalendarHeading(date: Date, view: "month" | "week") {
    if (view === "week") {
      const weekEnd = new Date(date);
      weekEnd.setDate(date.getDate() + 6);
      return `${new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date)} - ${new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(weekEnd)}`;
    }
    return new Intl.DateTimeFormat("en-US", {
      month: "long",
      year: "numeric",
    }).format(date);
  }

  function getDayAvailability(
    day: Date,
    dayAppointments: Appointment[],
    isDisabledBySchedule: boolean,
  ): { status: "available" | "booked" | "unavailable" | "limited"; label: string } {
    if (isDisabledBySchedule || day.getDay() === 0 || day.getDay() === 6) {
      return { status: "unavailable", label: "Unavailable" };
    }
    const nonCancelled = dayAppointments.filter(
      (apt) => apt.status !== "cancelled",
    );
    if (nonCancelled.length >= 3) {
      return { status: "booked", label: "Booked" };
    }
    if (nonCancelled.length > 0) {
      return { status: "limited", label: "Limited" };
    }
    return { status: "available", label: "Available" };
  }

  return (
    <div style={{ marginTop: "2rem" }}>
      {error && (
        <div className="status-message status-message--error" role="alert">
          <strong>We could not load your schedule.</strong>
          <span>{error}</span>
        </div>
      )}
      {isLoading && (
        <div className="status-message">Loading your calendar...</div>
      )}

      {!isLoading && !error && (
        <div className="provider-calendar-layout">
          <div className="provider-calendar-panel availability-widget">
            <div className="dashboard-panel__heading availability-widget__heading">
              <div>
                <p className="panel-kicker">Capacity planning</p>
                <h2>Availability calendar</h2>
              </div>
              <div className="availability-widget__controls">
                <div
                  className="availability-view-toggle"
                  role="group"
                  aria-label="Calendar view"
                >
                  {(["month", "week"] as const).map((view) => (
                    <button
                      className={calendarView === view ? "active" : ""}
                      key={view}
                      type="button"
                      aria-pressed={calendarView === view}
                      onClick={() => setCalendarView(view)}
                    >
                      {view}
                    </button>
                  ))}
                </div>
                <button
                  className="calendar-nav"
                  type="button"
                  aria-label="Previous period"
                  onClick={() => moveMonth(-1)}
                >
                  &#8592;
                </button>
                <button
                  className="calendar-nav"
                  type="button"
                  aria-label="Next period"
                  onClick={() => moveMonth(1)}
                >
                  &#8594;
                </button>
              </div>
            </div>

            <div className="availability-widget__meta">
              <strong>{formatCalendarHeading(calendarDays[0] || month, calendarView)}</strong>
              <div className="availability-legend">
                {(
                  ["available", "booked", "unavailable", "limited"] as const
                ).map((status) => (
                  <span key={status}>
                    <i
                      className={`availability-swatch availability-swatch--${status}`}
                    />
                    {status}
                  </span>
                ))}
              </div>
            </div>

            <div
              className={`availability-calendar availability-calendar--${calendarView}`}
              role="grid"
              aria-label={`${formatCalendarHeading(calendarDays[0] || month, calendarView)} availability`}
            >
              {calendarDays.map((day) => {
                const key = dateKey(day);
                const dayAppointments = appointmentsByDay[key] || [];
                const isCurrentMonth = day.getMonth() === month.getMonth();
                const isSelected = key === selectedDate;

                let isDisabled = false;
                if (scheduleData) {
                  const pythonDayOfWeek =
                    day.getDay() === 0 ? 6 : day.getDay() - 1;
                  const availabilityWindow = scheduleData.availability?.find(
                    (w: any) => w.day_of_week === pythonDayOfWeek,
                  );
                  if (
                    availabilityWindow &&
                    !availabilityWindow.is_working_day
                  ) {
                    isDisabled = true;
                  }

                  if (!isDisabled && scheduleData.blackout_dates) {
                    const isBlackout = scheduleData.blackout_dates.some(
                      (blackout: any) => {
                        const bStartKey = dateKey(
                          new Date(blackout.blackout_start),
                        );
                        const bEndKey = dateKey(
                          new Date(blackout.blackout_end),
                        );
                        return key >= bStartKey && key <= bEndKey;
                      },
                    );
                    if (isBlackout) {
                      isDisabled = true;
                    }
                  }
                }

                const { status, label } = getDayAvailability(
                  day,
                  dayAppointments,
                  isDisabled,
                );
                const nonCancelledCount = dayAppointments.filter(
                  (a) => a.status !== "cancelled",
                ).length;

                return (
                  <button
                    className={`availability-day availability-day--${status}${
                      calendarView === "month" && !isCurrentMonth
                        ? " availability-day--outside"
                        : ""
                    }${isSelected ? " calendar-day--selected" : ""}`}
                    key={key}
                    type="button"
                    role="gridcell"
                    aria-label={`${formatSelectedDate(key)}, ${dayAppointments.length} bookings, ${label}`}
                    onClick={() => {
                      setSelectedDate(key);
                    }}
                  >
                    <span>
                      {calendarView === "week" && (
                        <small>
                          {new Intl.DateTimeFormat("en-US", {
                            weekday: "short",
                          }).format(day)}
                        </small>
                      )}
                      {day.getDate()}
                    </span>
                    {nonCancelledCount > 0 && (
                      <strong>
                        {nonCancelledCount}{" "}
                        {nonCancelledCount === 1 ? "booking" : "bookings"}
                      </strong>
                    )}
                    <em>{label}</em>
                  </button>
                );
              })}
            </div>
          </div>

          <aside className="provider-agenda">
            <p className="panel-kicker">Day agenda</p>
            <h2>{formatSelectedDate(selectedDate)}</h2>
            {selectedAppointments.length > 0 ? (
              <div className="provider-agenda__list">
                {selectedAppointments.map((appointment) => (
                  <article
                    className={`provider-booking provider-booking--${appointment.status}`}
                    key={appointment.id}
                  >
                    <div>
                      <strong>
                        {formatTime(appointment.appointment_start)}
                      </strong>
                      <span>{appointment.duration_minutes} min</span>
                    </div>
                    <section>
                      <h3>
                        {services[appointment.service_id] || "Booked service"}
                      </h3>
                      <p>{appointment.user_name}</p>
                      <small>{appointment.user_email}</small>
                    </section>
                    <em>{appointment.status}</em>
                  </article>
                ))}
              </div>
            ) : (
              <div className="provider-agenda__empty">
                <span aria-hidden="true">+</span>
                <p>No bookings for this day.</p>
                <small>Choose another date to inspect the schedule.</small>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
