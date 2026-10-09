import { Link } from "react-router-dom";
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

export type PaymentFlowState =
  | "ready"
  | "creating-order"
  | "loading-checkout"
  | "verifying"
  | "confirmed"
  | "dismissed"
  | "failed"
  | "order-unknown"
  | "unknown";

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
  paymentFlowState: PaymentFlowState;
  recurringSeries: AppointmentSeriesResponse | null;
  recurrenceValidation: RecurrenceValidation;
  recurrenceOccurrences: RecurringOccurrence[];
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
  paymentFlowState,
  recurringSeries,
  recurrenceValidation,
  recurrenceOccurrences,
  confirmBooking,
  bookingError,
}: Props) {
  const recurrenceError =
    recurrenceValidation.errors.frequency ??
    recurrenceValidation.errors.occurrenceCount ??
    recurrenceValidation.errors.endDate;
  const paymentStatusMessage =
    bookingKind !== "ONE_TIME"
      ? null
      : paymentFlowState === "creating-order"
        ? "Creating your secure payment order..."
        : paymentFlowState === "loading-checkout"
          ? "Opening Razorpay Checkout..."
          : paymentFlowState === "verifying"
            ? "Payment received. Verifying it with the booking service..."
            : paymentFlowState === "unknown"
              ? "Your payment status could not be confirmed yet. Please don't retry payment while the server reconciles it."
              : paymentFlowState === "order-unknown"
                ? "We couldn't confirm whether a payment order was created. Please don't retry yet."
                : paymentFlowState === "dismissed"
                  ? "Checkout was closed; the appointment is not confirmed."
                  : null;

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
            : bookingKind === "ONE_TIME"
              ? "Appointment confirmed and paid"
              : "Booking request received"
          : "Review your booking"}
      </h2>
      <p>
        {isConfirmed && recurringSeries
          ? `All ${recurringSeries.occurrences.length} appointments in this series were created.`
          : isConfirmed
            ? bookingKind === "ONE_TIME"
              ? "Your payment was verified and your appointment is confirmed."
              : "Your appointment details are ready to be processed. We will follow up at the email address below."
            : "Everything looks good. Confirm the details below to request this appointment."}
      </p>
      {paymentStatusMessage && !isConfirmed && (
        <p className="status-message" role="status">
          {paymentStatusMessage}
        </p>
      )}
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
      <RecurringSchedulePreview
        bookingKind={bookingKind}
        occurrences={recurrenceOccurrences}
        validationError={recurrenceError}
      />
      {!isConfirmed && (
        <div className="booking-actions">
          <button
            className="secondary-button"
            disabled={
              bookingKind === "ONE_TIME" &&
              (isSubmitting || bookingOutcomeUnknown)
            }
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
                : paymentFlowState === "creating-order"
                  ? "Creating payment order..."
                  : paymentFlowState === "verifying"
                    ? "Verifying payment..."
                    : "Opening Checkout..."
              : bookingKind === "RECURRING"
                ? "Confirm recurring appointments"
                : paymentFlowState === "dismissed"
                  ? "Retry payment"
                  : paymentFlowState === "failed"
                    ? "Try payment again"
                    : "Pay and confirm booking"}{" "}
            <span aria-hidden="true">&#8594;</span>
          </button>
        </div>
      )}
      {bookingOutcomeUnknown && (
        <Link className="service-book-link" to="/appointments">
          {bookingKind === "ONE_TIME"
            ? "View appointments"
            : "Check My Appointments"}
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
