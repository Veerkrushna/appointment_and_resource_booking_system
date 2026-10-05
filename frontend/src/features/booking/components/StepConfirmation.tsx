import React from "react";
import { Link } from "react-router-dom";
import type {
  AvailabilitySlot,
  BookingDetails,
  BookingKind,
  Service,
} from "../types";
import type { AppointmentSeriesResponse } from "../../../lib/appointmentSeries";
import { formatDate, formatTime } from "../utils";

type Props = {
  isConfirmed: boolean;
  bookingKind: BookingKind;
  details: BookingDetails;
  selectedSlot: AvailabilitySlot | null;
  service: Service;
  date: string;
  setStep: (step: number) => void;
  isSubmitting: boolean;
  bookingOutcomeUnknown: boolean;
  recurringSeries: AppointmentSeriesResponse | null;
  confirmBooking: () => void;
  bookingError: string | null;
};

export default function StepConfirmation({
  isConfirmed,
  bookingKind,
  details,
  selectedSlot,
  service,
  date,
  setStep,
  isSubmitting,
  bookingOutcomeUnknown,
  recurringSeries,
  confirmBooking,
  bookingError,
}: Props) {
  return (
    <div className="confirmation-panel">
      <span className="confirmation-mark" aria-hidden="true">
        &#10003;
      </span>
      <p className="panel-kicker">Step 3 of 3</p>
      <h2>
        {isConfirmed
          ? recurringSeries
            ? "Recurring appointments created"
            : "Booking request received"
          : "Review your booking"}
      </h2>
      <p>
        {isConfirmed && recurringSeries
          ? `All ${recurringSeries.occurrences.length} appointments in this series were created.`
          : isConfirmed
            ? "Your appointment details are ready to be processed. We will follow up at the email address below."
            : "Everything looks good. Confirm the details below to request this appointment."}
      </p>
      <div className="confirmation-details">
        <strong>
          {isConfirmed ? "Booked for" : "Appointment for"}: {details.name}
        </strong>
        <span>{details.email}</span>
        <span>Provider: {selectedSlot?.provider_name || "Not selected"}</span>
        <span>Service: {service.name}</span>
        <span>
          {formatDate(date)} at{" "}
          {selectedSlot ? formatTime(selectedSlot.start) : "Not selected"}
        </span>
        {recurringSeries && (
          <>
            <span>Series ID: {recurringSeries.id}</span>
            <span>
              {recurringSeries.occurrences.length} scheduled appointments
            </span>
            <span>Provider timezone: {recurringSeries.timezone}</span>
          </>
        )}
      </div>
      {!isConfirmed && (
        <div className="booking-actions">
          <button
            className="secondary-button"
            onClick={() => setStep(2)}
            type="button"
          >
            Edit details
          </button>
          <button
            className="primary-button"
            disabled={isSubmitting || bookingOutcomeUnknown}
            onClick={() => void confirmBooking()}
            type="button"
          >
            {isSubmitting
              ? bookingKind === "RECURRING"
                ? "Creating series..."
                : "Saving booking..."
              : bookingKind === "RECURRING"
                ? "Confirm recurring appointments"
                : "Confirm booking"}{" "}
            <span aria-hidden="true">&#8594;</span>
          </button>
        </div>
      )}
      {bookingOutcomeUnknown && (
        <Link className="service-book-link" to="/appointments">
          Check My Appointments
        </Link>
      )}
      {bookingError && (
        <p className="status-message status-message--error" role="alert">
          {bookingError}
        </p>
      )}
      {isConfirmed && (
        <Link className="service-book-link" to="/appointments">
          View appointments <span aria-hidden="true">&#8594;</span>
        </Link>
      )}
    </div>
  );
}
