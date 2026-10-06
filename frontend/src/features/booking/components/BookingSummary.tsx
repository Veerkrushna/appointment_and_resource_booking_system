import React from "react";
import type {
  AvailabilitySlot,
  BookingKind,
  RecurrenceOptionsValue,
  Service,
} from "../types";
import { formatDate, formatTime } from "../utils";

type Props = {
  service: Service;
  selectedSlot: AvailabilitySlot | null;
  date: string;
  bookingKind: BookingKind;
  recurrence: RecurrenceOptionsValue;
};

export default function BookingSummary({
  service,
  selectedSlot,
  date,
  bookingKind,
  recurrence,
}: Props) {
  const recurrenceLabel =
    recurrence.frequency === "MONTHLY"
      ? "Monthly"
      : recurrence.interval === 2
        ? "Every 2 weeks"
        : "Weekly";

  return (
    <aside className="booking-summary">
      <p className="summary-label">Your selection</p>
      <h2>{service.name}</h2>
      <p>
        {service.description ||
          "Appointment details will be confirmed with your provider."}
      </p>
      <dl>
        <div>
          <dt>Provider</dt>
          <dd>{selectedSlot?.provider_name || "Not selected"}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{service.duration_minutes} min</dd>
        </div>
        <div>
          <dt>Date</dt>
          <dd>{date ? formatDate(date) : "Not selected"}</dd>
        </div>
        <div>
          <dt>Time</dt>
          <dd>
            {selectedSlot ? formatTime(selectedSlot.start) : "Not selected"}
          </dd>
        </div>
        {bookingKind === "RECURRING" && (
          <>
            <div>
              <dt>Repeats</dt>
              <dd>{recurrenceLabel}</dd>
            </div>
            <div>
              <dt>Ends</dt>
              <dd>
                {recurrence.endMode === "COUNT"
                  ? recurrence.occurrenceCount == null
                    ? "Choose number of visits"
                    : `After ${recurrence.occurrenceCount} visits`
                  : recurrence.endDate
                    ? formatDate(recurrence.endDate)
                    : "Choose an end date"}
              </dd>
            </div>
          </>
        )}
      </dl>
    </aside>
  );
}
