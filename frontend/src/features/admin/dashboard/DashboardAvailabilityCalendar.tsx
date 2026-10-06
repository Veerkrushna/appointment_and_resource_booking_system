import { useMemo, useState } from "react";

type CalendarView = "month" | "week";
type AvailabilityStatus = "available" | "booked" | "unavailable" | "limited";

function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function getCalendarDays(date: Date, view: CalendarView) {
  const start = new Date(
    date.getFullYear(),
    date.getMonth(),
    view === "month" ? 1 : date.getDate(),
  );
  start.setDate(start.getDate() - start.getDay());
  return Array.from({ length: view === "month" ? 42 : 7 }, (_, index) => {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    return day;
  });
}

function availabilityStatus(
  date: Date,
  bookingCount: number,
): AvailabilityStatus {
  if (date.getDay() === 0 || date.getDay() === 6) return "unavailable";
  if (bookingCount >= 3) return "booked";
  if (bookingCount > 0) return "limited";
  return "available";
}

function formatCalendarLabel(date: Date, view: CalendarView) {
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

type Props = {
  appointmentsByDay: Record<string, number>;
};

export default function DashboardAvailabilityCalendar({
  appointmentsByDay,
}: Props) {
  const [calendarView, setCalendarView] = useState<CalendarView>("month");
  const [calendarDate, setCalendarDate] = useState(() => new Date());

  const calendarDays = useMemo(
    () => getCalendarDays(calendarDate, calendarView),
    [calendarDate, calendarView],
  );

  function moveCalendar(amount: number) {
    setCalendarDate((current) => {
      const next = new Date(current);
      next.setDate(
        current.getDate() +
          (calendarView === "month" ? amount * 31 : amount * 7),
      );
      return next;
    });
  }

  return (
    <section className="dashboard-panel availability-widget">
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
            {(["month", "week"] as CalendarView[]).map((view) => (
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
            onClick={() => moveCalendar(-1)}
          >
            &#8592;
          </button>
          <button
            className="calendar-nav"
            type="button"
            aria-label="Next period"
            onClick={() => moveCalendar(1)}
          >
            &#8594;
          </button>
        </div>
      </div>
      <div className="availability-widget__meta">
        <strong>{formatCalendarLabel(calendarDays[0], calendarView)}</strong>
        <div className="availability-legend">
          {(
            ["available", "booked", "unavailable", "limited"] as AvailabilityStatus[]
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
        aria-label={`${formatCalendarLabel(calendarDays[0], calendarView)} availability`}
      >
        {calendarDays.map((day) => {
          const count = appointmentsByDay[dateKey(day)] || 0;
          const status = availabilityStatus(day, count);
          const isCurrentMonth = day.getMonth() === calendarDate.getMonth();
          return (
            <div
              className={`availability-day availability-day--${status}${
                calendarView === "month" && !isCurrentMonth
                  ? " availability-day--outside"
                  : ""
              }`}
              key={dateKey(day)}
              role="gridcell"
              aria-label={`${day.toLocaleDateString("en-US", {
                month: "long",
                day: "numeric",
              })}: ${status}`}
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
              {count > 0 && (
                <strong>
                  {count} {count === 1 ? "booking" : "bookings"}
                </strong>
              )}
              <em>{status}</em>
            </div>
          );
        })}
      </div>
    </section>
  );
}
