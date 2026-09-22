import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/useAuth";

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

  const lastDay = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const end = new Date(lastDay);
  end.setDate(lastDay.getDate() + (6 - lastDay.getDay()));

  const totalDays = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;

  return Array.from({ length: totalDays }, (_, index) => {
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

export default function ProviderCalendarPage() {
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
        const providersResponse = await fetch('/api/providers');
        if (!providersResponse.ok) throw new Error(await responseMessage(providersResponse, "Unable to load providers."));
        const providers = await providersResponse.json();
        const provider = providers.find((p: any) => p.email === customer.email);

        if (!provider) {
          setAppointments([]);
          setServices({});
          setIsLoading(false);
          return;
        }

        const [appointmentsResponse, servicesResponse, scheduleResponse] = await Promise.all([
          fetch(`/api/appointments?provider_id=${provider.id}`, {
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          }),
          fetch("/api/services"),
          fetch(`/api/providers/${provider.id}/schedule`)
        ]);
        
        if (scheduleResponse.ok) {
          const schedule = await scheduleResponse.json();
          setScheduleData(schedule);
        }
        
        if (!appointmentsResponse.ok) throw new Error(await responseMessage(appointmentsResponse, "Unable to load bookings."));
        const appointmentsData = await appointmentsResponse.json();
        setAppointments(appointmentsData.appointments || []);
        
        if (servicesResponse.ok) {
          const serviceData: Service[] = await servicesResponse.json();
          setServices(Object.fromEntries(serviceData.map((service) => [service.id, service.name])));
        }
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Unable to load calendar data.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadData();
  }, [customer?.id, token]);

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

  function moveMonth(amount: number) {
    setMonth((current) => new Date(current.getFullYear(), current.getMonth() + amount, 1));
  }

  return (
    <section className="dashboard-page">
      <header className="dashboard-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <p className="eyebrow">Schedule</p>
          <h1>My Calendar</h1>
          <p className="services-intro">Manage your appointments, available slots, and breaks.</p>
        </div>
        {!isLoading && !error && (
          <p className="service-count">
            <strong>{appointments.filter((appointment) => appointment.status !== "cancelled").length}</strong> active bookings
          </p>
        )}
      </header>

      {error && <div className="status-message status-message--error" role="alert"><strong>We could not load your schedule.</strong><span>{error}</span></div>}
      {isLoading && <div className="status-message">Loading your calendar...</div>}

      {!isLoading && !error && (
        <div className="provider-calendar-layout">
          <div className="provider-calendar-panel">
            <div className="calendar-header">
              <button className="calendar-nav" type="button" aria-label="Previous month" onClick={() => moveMonth(-1)}>&#8592;</button>
              <h2>{formatMonth(month)}</h2>
              <button className="calendar-nav" type="button" aria-label="Next month" onClick={() => moveMonth(1)}>&#8594;</button>
            </div>
            <div className="calendar-weekdays" aria-hidden="true">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <span key={day}>{day}</span>)}
            </div>
            <div className="calendar-grid" role="grid" aria-label={`${formatMonth(month)} schedule`}>
              {calendarDays.map((day) => {
                const key = dateKey(day);
                const dayAppointments = appointmentsByDay[key] || [];
                const isCurrentMonth = day.getMonth() === month.getMonth();
                const isSelected = key === selectedDate;
                
                let isDisabled = false;
                if (scheduleData) {
                  const pythonDayOfWeek = day.getDay() === 0 ? 6 : day.getDay() - 1;
                  const availabilityWindow = scheduleData.availability?.find((w: any) => w.day_of_week === pythonDayOfWeek);
                  if (availabilityWindow && !availabilityWindow.is_working_day) {
                    isDisabled = true;
                  }
                  
                  if (!isDisabled && scheduleData.blackout_dates) {
                    const isBlackout = scheduleData.blackout_dates.some((blackout: any) => {
                      const bStartKey = dateKey(new Date(blackout.blackout_start));
                      const bEndKey = dateKey(new Date(blackout.blackout_end));
                      return key >= bStartKey && key <= bEndKey;
                    });
                    if (isBlackout) {
                      isDisabled = true;
                    }
                  }
                }

                return (
                  <button 
                    className={`calendar-day${isCurrentMonth ? "" : " calendar-day--outside"}${isSelected ? " calendar-day--selected" : ""}`} 
                    key={key} 
                    type="button" 
                    role="gridcell" 
                    aria-label={`${formatSelectedDate(key)}, ${dayAppointments.length} bookings`} 
                    onClick={() => {
                      if (!isDisabled) setSelectedDate(key);
                    }}
                    disabled={isDisabled}
                  >
                    <span>{day.getDate()}</span>
                    {dayAppointments.length > 0 && <small className="calendar-day__count">{dayAppointments.length}</small>}
                    <div className="calendar-day__dots">
                      {dayAppointments.slice(0, 3).map((appointment) => (
                        <i className={`calendar-dot calendar-dot--${appointment.status}`} key={appointment.id} />
                      ))}
                    </div>
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
                  <article className={`provider-booking provider-booking--${appointment.status}`} key={appointment.id}>
                    <div>
                      <strong>{formatTime(appointment.appointment_start)}</strong>
                      <span>{appointment.duration_minutes} min</span>
                    </div>
                    <section>
                      <h3>{services[appointment.service_id] || "Booked service"}</h3>
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
    </section>
  );
}
