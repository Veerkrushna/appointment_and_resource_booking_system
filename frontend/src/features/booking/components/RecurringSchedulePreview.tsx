import type { BookingKind } from "../types";
import type { RecurringOccurrence } from "../recurrence";

type Props = {
  bookingKind: BookingKind;
  occurrences: RecurringOccurrence[];
  validationError?: string;
};

function formatOccurrenceDate(date: string): string {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T00:00:00.000Z`));
}

function formatLocalStartTime(localStartTime: string): string {
  const [hours, minutes] = localStartTime.split(":").map(Number);
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(2000, 0, 1, hours, minutes)));
}

export default function RecurringSchedulePreview({
  bookingKind,
  occurrences,
  validationError,
}: Props) {
  if (bookingKind !== "RECURRING") {
    return null;
  }
  if (!validationError && occurrences.length === 0) {
    return null;
  }

  return (
    <section
      aria-labelledby="recurring-schedule-heading"
      className="recurring-schedule"
    >
      <h3 id="recurring-schedule-heading">
        Recurring schedule · {occurrences.length}{" "}
        {occurrences.length === 1 ? "appointment" : "appointments"}
      </h3>
      {validationError ? (
        <p className="status-message status-message--error" role="alert">
          {validationError}
        </p>
      ) : (
        <ol
          aria-label="Scheduled appointments"
          className="recurring-schedule__list"
        >
          {occurrences.map((occurrence) => (
            <li
              className="recurring-schedule__item"
              key={occurrence.occurrenceNumber}
            >
              <span className="recurring-schedule__number">
                #{occurrence.occurrenceNumber}
              </span>
              <span className="recurring-schedule__date">
                {formatOccurrenceDate(occurrence.date)}
              </span>
              <span className="recurring-schedule__time">
                {formatLocalStartTime(occurrence.localStartTime)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
