import React from "react";
import { Service, AvailabilitySlot } from "../types";
import { formatDate, formatTime } from "../utils";

type Props = {
  service: Service;
  selectedSlot: AvailabilitySlot | null;
  date: string;
};

export default function BookingSummary({ service, selectedSlot, date }: Props) {
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
      </dl>
    </aside>
  );
}
