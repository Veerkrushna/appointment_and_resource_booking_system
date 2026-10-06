import React from "react";
import { Link } from "react-router-dom";
import ProviderRatingSelect from "../../../components/ProviderRatingSelect";
import RecurrenceOptions from "./RecurrenceOptions";
import type {
  AvailabilitySlot,
  BookingKind,
  ProviderOption,
  ProviderType,
  RecurrenceAccess,
  RecurrenceOptionsValue,
  RecurrenceValidation,
} from "../types";
import { formatDate, formatTime, getToday } from "../utils";

type Props = {
  date: string;
  setDate: (date: string) => void;
  selectedSlot: AvailabilitySlot | null;
  setSelectedSlot: (slot: AvailabilitySlot | null) => void;
  availableSlots: AvailabilitySlot[];
  providerOptions: ProviderOption[];
  providerTypes: Record<string, ProviderType>;
  selectedProviderId: string;
  handleProviderChange: (providerId: string) => void;
  availabilityLoading: boolean;
  availabilityError: string | null;
  setAvailableSlots: (slots: AvailabilitySlot[]) => void;
  setAvailabilityError: (error: string | null) => void;
  setAvailabilityLoading: (loading: boolean) => void;
  bookingKind: BookingKind;
  setBookingKind: (kind: BookingKind) => void;
  recurrence: RecurrenceOptionsValue;
  setRecurrence: (value: RecurrenceOptionsValue) => void;
  recurrenceValidation: RecurrenceValidation;
  recurrenceAccess: RecurrenceAccess;
  selectedProviderTimezone: string | null;
  providerTimezonesLoaded: boolean;
  setStep: (step: number) => void;
};

export default function StepDateTime({
  date,
  setDate,
  selectedSlot,
  setSelectedSlot,
  availableSlots,
  providerOptions,
  providerTypes,
  selectedProviderId,
  handleProviderChange,
  availabilityLoading,
  availabilityError,
  setAvailableSlots,
  setAvailabilityError,
  setAvailabilityLoading,
  bookingKind,
  setBookingKind,
  recurrence,
  setRecurrence,
  recurrenceValidation,
  recurrenceAccess,
  selectedProviderTimezone,
  providerTimezonesLoaded,
  setStep,
}: Props) {
  const canBookRecurring = recurrenceAccess === "customer";
  const canContinue =
    Boolean(date && selectedSlot) &&
    (bookingKind === "ONE_TIME" ||
      (canBookRecurring &&
        recurrenceValidation.isValid &&
        Boolean(selectedProviderTimezone)));

  return (
    <div>
      <p className="panel-kicker">Step 1 of 3</p>
      <h2>Select a date and time</h2>
      <div className="booking-date-selection">
        <label className="field-label" htmlFor="booking-date">
          Preferred date
        </label>
        <input
          className="date-input"
          id="booking-date"
          min={getToday()}
          onChange={(event) => {
            const nextDate = event.target.value;
            if (nextDate !== date && selectedSlot) {
              setSelectedSlot(null);
            }
            setDate(nextDate);
            if (!nextDate) {
              setAvailableSlots([]);
              setSelectedSlot(null);
              setAvailabilityError(null);
              setAvailabilityLoading(false);
            }
          }}
          type="date"
          value={date}
        />

        {date && (
          <div className="time-selection">
            <div className="time-selection__heading">
              <span>Available times</span>
              <small>{formatDate(date)}</small>
            </div>
            <ProviderRatingSelect
              providers={providerOptions}
              providerTypes={providerTypes}
              selectedProviderId={selectedProviderId}
              disabled={availabilityLoading}
              onChange={handleProviderChange}
            />
            {availabilityLoading && (
              <p className="status-message">Loading available times...</p>
            )}
            {availabilityError && (
              <p className="status-message status-message--error" role="alert">
                {availabilityError}
              </p>
            )}
            {!availabilityLoading &&
              !availabilityError &&
              availableSlots.length === 0 && (
                <p className="status-message">
                  {selectedProviderId
                    ? `No available appointments for ${providerOptions.find((provider) => provider.id === selectedProviderId)?.name ?? "this provider"} on this date.`
                    : "No available times for this date."}
                </p>
              )}
            {!availabilityLoading &&
              !availabilityError &&
              availableSlots.length > 0 && (
                <div className="time-grid">
                  {availableSlots.map((slot) => (
                    <button
                      className={
                        selectedSlot?.start === slot.start &&
                        selectedSlot.provider_id === slot.provider_id
                          ? "time-button active"
                          : "time-button"
                      }
                      key={`${slot.provider_id}-${slot.start}`}
                      onClick={() => setSelectedSlot(slot)}
                      type="button"
                    >
                      <span>{formatTime(slot.start)}</span>
                      <small>{slot.provider_name}</small>
                    </button>
                  ))}
                </div>
              )}
          </div>
        )}
      </div>

      <div
        className="booking-mode-toggle"
        role="radiogroup"
        aria-label="Booking type"
      >
        <label
          className={`booking-mode-option ${bookingKind === "ONE_TIME" ? "selected" : ""}`}
        >
          <input
            checked={bookingKind === "ONE_TIME"}
            name="booking-kind"
            onChange={() => setBookingKind("ONE_TIME")}
            type="radio"
          />
          <span className="booking-mode-copy">
            <span className="booking-mode-title">One-time</span>
          </span>
        </label>
        <label
          className={`booking-mode-option ${bookingKind === "RECURRING" ? "selected" : ""}`}
        >
          <input
            checked={bookingKind === "RECURRING"}
            disabled={!canBookRecurring}
            name="booking-kind"
            onChange={() => setBookingKind("RECURRING")}
            type="radio"
          />
          <span className="booking-mode-copy">
            <span className="booking-mode-title">Recurring</span>
          </span>
        </label>
      </div>

      {recurrenceAccess === "loading" && (
        <p className="status-message">
          Checking your account for recurring booking...
        </p>
      )}
      {recurrenceAccess === "guest" && (
        <p className="status-message">
          Sign in with a customer account to book recurring appointments.{" "}
          <Link to="/login">Sign in</Link>
        </p>
      )}
      {recurrenceAccess === "unavailable" && (
        <p className="status-message">
          Recurring booking is available to customers only.
        </p>
      )}

      {bookingKind === "RECURRING" && (
        <>
          <RecurrenceOptions
            value={recurrence}
            onChange={setRecurrence}
            startDate={selectedSlot?.date || date}
          />
          {selectedSlot && selectedProviderTimezone ? (
            <p className="status-message">
              Recurring times follow the provider timezone:{" "}
              {selectedProviderTimezone}.
            </p>
          ) : selectedSlot && !providerTimezonesLoaded ? (
            <p className="status-message">Loading provider timezone...</p>
          ) : selectedSlot ? (
            <p className="status-message status-message--error" role="alert">
              The provider timezone is unavailable, so recurring booking cannot
              continue.
            </p>
          ) : null}
        </>
      )}

      <button
        className="primary-button"
        disabled={!canContinue}
        onClick={() => setStep(2)}
        type="button"
      >
        Continue to details <span aria-hidden="true">&#8594;</span>
      </button>
    </div>
  );
}
