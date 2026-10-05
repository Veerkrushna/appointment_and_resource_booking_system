import React from "react";
import ProviderRatingSelect from "../../../components/ProviderRatingSelect";
import type { AvailabilitySlot, ProviderOption, ProviderType } from "../types";
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
  setStep,
}: Props) {
  return (
    <div>
      <p className="panel-kicker">Step 1 of 3</p>
      <h2>Select a date and time</h2>
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

      <button
        className="primary-button"
        disabled={!date || !selectedSlot}
        onClick={() => setStep(2)}
        type="button"
      >
        Continue to details <span aria-hidden="true">&#8594;</span>
      </button>
    </div>
  );
}
