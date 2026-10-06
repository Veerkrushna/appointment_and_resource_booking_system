import { useState } from "react";
import { Link } from "react-router-dom";
import PayButton from "../../../components/PayButton";
import type {
  AvailabilitySlot,
  BookingDetails,
  BookingKind,
  RecurrenceValidation,
  Service,
} from "../types";
import type { AppointmentSeriesResponse } from "../../../lib/appointmentSeries";
import type { RecurringOccurrence } from "../recurrence";
import { formatDate, formatTime } from "../utils";
import RecurringSchedulePreview from "./RecurringSchedulePreview";

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
  recurrenceValidation: RecurrenceValidation;
  recurrenceOccurrences: RecurringOccurrence[];
  confirmBooking: () => void;
  bookingError: string | null;
  createdBookingId?: string | null;
  bookingStatus?: "Pending" | "Confirmed" | "Payment failed" | null;
  onPaid?: () => void;
  onPaymentFailed?: (errorMessage: string) => void;
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
  recurrenceValidation,
  recurrenceOccurrences,
  confirmBooking,
  bookingError,
  createdBookingId,
  bookingStatus,
  onPaid,
  onPaymentFailed,
}: Props) {
  const [isConfirmingAtAppointment, setIsConfirmingAtAppointment] =
    useState(false);
  const [payAtAppointmentError, setPayAtAppointmentError] = useState<
    string | null
  >(null);
  const [confirmedViaPayAtAppointment, setConfirmedViaPayAtAppointment] =
    useState(false);

  const recurrenceError =
    recurrenceValidation.errors.frequency ??
    recurrenceValidation.errors.occurrenceCount ??
    recurrenceValidation.errors.endDate;

  const displayPrice =
    service.price != null && Number(service.price) > 0
      ? `₹${Number(service.price).toFixed(2)}`
      : "₹500.00 (Demo)";

  async function handlePayAtAppointment() {
    if (!createdBookingId || isConfirmingAtAppointment) return;

    setIsConfirmingAtAppointment(true);
    setPayAtAppointmentError(null);
    try {
      const response = await fetch("/payments/pay-at-appointment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ booking_id: createdBookingId }),
      });

      if (!response.ok) {
        let errMsg = "Failed to confirm appointment.";
        try {
          const errData = await response.json();
          if (errData.detail) errMsg = errData.detail;
        } catch {
          // fallback
        }
        throw new Error(errMsg);
      }

      setConfirmedViaPayAtAppointment(true);
      onPaid?.();
    } catch (err) {
      setPayAtAppointmentError(
        err instanceof Error ? err.message : "Failed to confirm appointment.",
      );
    } finally {
      setIsConfirmingAtAppointment(false);
    }
  }

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
            : "Booking Confirmed"
          : createdBookingId
            ? bookingStatus === "Payment failed"
              ? "Payment Failed"
              : "Choose Payment Method"
            : "Review your booking"}
      </h2>
      <p>
        {isConfirmed && recurringSeries
          ? `All ${recurringSeries.occurrences.length} appointments in this series were created.`
          : isConfirmed
            ? confirmedViaPayAtAppointment
              ? `Your appointment is confirmed! Please pay ${displayPrice} at your visit.`
              : "Your payment was verified and appointment confirmed! A confirmation email has been dispatched."
            : createdBookingId
              ? "Your slot is held for 10 minutes. Choose your payment method below to finalize your booking."
              : "Everything looks good. Proceed to payments to reserve this appointment."}
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
        <span>Amount: {displayPrice}</span>

        {/* Dynamic Booking Status */}
        {(bookingStatus || isConfirmed) && (
          <div
            style={{
              marginTop: "0.75rem",
              paddingTop: "0.5rem",
              borderTop: "1px solid rgba(0, 0, 0, 0.08)",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <span style={{ fontWeight: 600 }}>Booking status:</span>
            <span
              style={{
                display: "inline-block",
                padding: "0.2rem 0.65rem",
                borderRadius: "9999px",
                fontSize: "0.85rem",
                fontWeight: 600,
                backgroundColor:
                  isConfirmed || bookingStatus === "Confirmed"
                    ? "#dcfce7"
                    : bookingStatus === "Payment failed"
                      ? "#fee2e2"
                      : "#fef3c7",
                color:
                  isConfirmed || bookingStatus === "Confirmed"
                    ? "#166534"
                    : bookingStatus === "Payment failed"
                      ? "#991b1b"
                      : "#92400e",
              }}
            >
              {isConfirmed
                ? "Confirmed"
                : bookingStatus || "Pending"}
            </span>
            {isConfirmed && confirmedViaPayAtAppointment && (
              <span style={{ fontSize: "0.8rem", color: "#475569" }}>
                (Pay at Appointment)
              </span>
            )}
          </div>
        )}

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

      <RecurringSchedulePreview
        bookingKind={bookingKind}
        occurrences={recurrenceOccurrences}
        validationError={recurrenceError}
      />

      {/* Show 2 payment options when user clicked "Proceed with payments" */}
      {createdBookingId && !isConfirmed && (
        <div
          style={{
            marginTop: "1.5rem",
            padding: "1.25rem",
            borderRadius: "0.75rem",
            backgroundColor: "#ffffff",
            border: "1px solid #e2e8f0",
            boxShadow: "0 1px 3px rgba(0, 0, 0, 0.05)",
          }}
        >
          <h3
            style={{
              fontSize: "1.1rem",
              fontWeight: 700,
              color: "#0f172a",
              marginBottom: "0.25rem",
            }}
          >
            Select Payment Option
          </h3>
          <p
            style={{
              fontSize: "0.875rem",
              color: "#64748b",
              marginBottom: "1.25rem",
            }}
          >
            Choose how you would like to complete your payment for this appointment:
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: "1rem",
              marginBottom: "1rem",
            }}
          >
            {/* Option 1: Pay with Razorpay */}
            <div
              style={{
                border: "1px solid #cbd5e1",
                borderRadius: "0.5rem",
                padding: "1rem",
                backgroundColor: "#f8fafc",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
              }}
            >
              <div>
                <strong
                  style={{
                    display: "block",
                    fontSize: "1rem",
                    color: "#1e293b",
                    marginBottom: "0.35rem",
                  }}
                >
                  1) Pay with razorpay
                </strong>
                <p
                  style={{
                    fontSize: "0.825rem",
                    color: "#475569",
                    marginBottom: "1rem",
                    lineHeight: 1.4,
                  }}
                >
                  Pay online instantly via UPI or card (Demo / Test Mode).
                </p>
              </div>

              <div>
                <PayButton
                  bookingId={createdBookingId}
                  onPaid={() => onPaid?.()}
                  onPaymentFailed={(msg) => onPaymentFailed?.(msg)}
                  customerName={details.name}
                  customerEmail={details.email}
                  customerPhone={details.phone}
                />
                <p
                  style={{
                    fontSize: "0.75rem",
                    color: "#64748b",
                    marginTop: "0.5rem",
                    lineHeight: 1.3,
                  }}
                >
                  Test UPI IDs:{" "}
                  <code style={{ background: "#e2e8f0", padding: "1px 3px" }}>
                    success@razorpay
                  </code>{" "}
                  /{" "}
                  <code style={{ background: "#e2e8f0", padding: "1px 3px" }}>
                    failure@razorpay
                  </code>
                </p>
              </div>
            </div>

            {/* Option 2: Pay at Appointment */}
            <div
              style={{
                border: "1px solid #cbd5e1",
                borderRadius: "0.5rem",
                padding: "1rem",
                backgroundColor: "#f8fafc",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
              }}
            >
              <div>
                <strong
                  style={{
                    display: "block",
                    fontSize: "1rem",
                    color: "#1e293b",
                    marginBottom: "0.35rem",
                  }}
                >
                  2) Pay at Appointment
                </strong>
                <p
                  style={{
                    fontSize: "0.825rem",
                    color: "#475569",
                    marginBottom: "1rem",
                    lineHeight: 1.4,
                  }}
                >
                  Pay at the venue with cash, card, or UPI upon your arrival.
                </p>
              </div>

              <div>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={isConfirmingAtAppointment}
                  onClick={() => void handlePayAtAppointment()}
                  style={{
                    width: "100%",
                    padding: "0.5rem 1rem",
                    fontWeight: 600,
                  }}
                >
                  {isConfirmingAtAppointment
                    ? "Confirming appointment..."
                    : "Pay at Appointment"}
                </button>
                <p
                  style={{
                    fontSize: "0.75rem",
                    color: "#166534",
                    marginTop: "0.5rem",
                    fontWeight: 500,
                  }}
                >
                  ✓ Confirms appointment immediately
                </p>
              </div>
            </div>
          </div>

          {payAtAppointmentError && (
            <p
              className="status-message status-message--error"
              role="alert"
              style={{ marginTop: "0.5rem" }}
            >
              {payAtAppointmentError}
            </p>
          )}

          <div style={{ marginTop: "1rem", textAlign: "right" }}>
            <button
              className="secondary-button"
              onClick={() => setStep(2)}
              type="button"
            >
              Edit details
            </button>
          </div>
        </div>
      )}

      {/* Initial submission before booking row is created */}
      {!createdBookingId && !isConfirmed && (
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
            disabled={
              isSubmitting ||
              bookingOutcomeUnknown ||
              (bookingKind === "RECURRING" && !recurrenceValidation.isValid)
            }
            onClick={() => void confirmBooking()}
            type="button"
          >
            {isSubmitting
              ? bookingKind === "RECURRING"
                ? "Creating series..."
                : "Holding slot..."
              : bookingKind === "RECURRING"
                ? "Confirm recurring appointments"
                : "Proceed with payments"}{" "}
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
