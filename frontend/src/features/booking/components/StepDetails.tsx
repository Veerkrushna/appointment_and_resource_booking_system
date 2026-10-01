import React, { FormEvent } from "react";
import { BookingDetails } from "../types";

type Props = {
  hasAuthenticatedCustomer: boolean;
  bookingMode: "self" | "other";
  applyBookingMode: (mode: "self" | "other") => void;
  details: BookingDetails;
  handleDetailsChange: (field: keyof BookingDetails, value: string) => void;
  submitDetails: (event: FormEvent<HTMLFormElement>) => void;
  bookingError: string | null;
  setStep: (step: number) => void;
};

export default function StepDetails({
  hasAuthenticatedCustomer,
  bookingMode,
  applyBookingMode,
  details,
  handleDetailsChange,
  submitDetails,
  bookingError,
  setStep,
}: Props) {
  return (
    <form noValidate onSubmit={submitDetails}>
      <p className="panel-kicker">Step 2 of 3</p>
      <h2>Who is this appointment for?</h2>

      {hasAuthenticatedCustomer && (
        <div
          className="booking-mode-toggle"
          role="radiogroup"
          aria-label="Appointment booking recipient"
        >
          <label
            className={`booking-mode-option ${bookingMode === "self" ? "selected" : ""}`}
          >
            <input
              checked={bookingMode === "self"}
              onChange={() => applyBookingMode("self")}
              type="radio"
            />
            <span className="booking-mode-copy">
              <span className="booking-mode-title">Book for myself</span>
              <span className="booking-mode-description">
                Use my account details
              </span>
            </span>
          </label>
          <label
            className={`booking-mode-option ${bookingMode === "other" ? "selected" : ""}`}
          >
            <input
              checked={bookingMode === "other"}
              onChange={() => applyBookingMode("other")}
              type="radio"
            />
            <span className="booking-mode-copy">
              <span className="booking-mode-title">Book for someone else</span>
              <span className="booking-mode-description">
                Enter their contact details
              </span>
            </span>
          </label>
        </div>
      )}

      <div className="form-grid">
        <label className="field-label">
          Full name
          <input
            required
            onChange={(event) => handleDetailsChange("name", event.target.value)}
            type="text"
            value={details.name}
          />
        </label>
        <label className="field-label">
          Email address
          <input
            required
            aria-describedby="booking-email-error"
            onChange={(event) => handleDetailsChange("email", event.target.value)}
            type="email"
            value={details.email}
          />
        </label>
        <label className="field-label">
          Phone number <span>(optional)</span>
          <input
            onChange={(event) => handleDetailsChange("phone", event.target.value)}
            type="tel"
            value={details.phone}
          />
        </label>
        <label className="field-label">
          Notes <span>(optional)</span>
          <textarea
            onChange={(event) => handleDetailsChange("notes", event.target.value)}
            rows={4}
            value={details.notes}
          />
        </label>
      </div>
      {bookingError && (
        <p
          className="status-message status-message--error"
          id="booking-email-error"
          role="alert"
        >
          {bookingError}
        </p>
      )}
      <div className="booking-actions">
        <button
          className="secondary-button"
          onClick={() => setStep(1)}
          type="button"
        >
          Back
        </button>
        <button className="primary-button" type="submit">
          Review booking <span aria-hidden="true">&#8594;</span>
        </button>
      </div>
    </form>
  );
}
