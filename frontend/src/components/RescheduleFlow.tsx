import { useEffect, useState } from "react";
import type { CustomerAppointment } from "../lib/customerAppointments";
import {
  getMessage,
  rescheduleCustomerAppointment,
} from "../lib/customerAppointments";

type AvailabilitySlot = {
  provider_id: string;
  start: string;
  end: string;
};

type Props = {
  appointment: CustomerAppointment;
  serviceName: string;
  providerName: string;
  token: string;
  onComplete: () => Promise<void> | void;
  onCancel: () => void;
};

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function toDateInput(value: string) {
  return new Date(value).toISOString().slice(0, 10);
}

function RescheduleFlow({
  appointment,
  serviceName,
  providerName,
  token,
  onComplete,
  onCancel,
}: Props) {
  const [date, setDate] = useState(toDateInput(appointment.appointment_start));
  const [slots, setSlots] = useState<AvailabilitySlot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<AvailabilitySlot | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState<"date" | "confirm">("date");

  useEffect(() => {
    if (!date) return;
    let isCurrent = true;
    async function loadSlots() {
      setIsLoading(true);
      setError("");
      setSelectedSlot(null);
      try {
        const query = new URLSearchParams({
          service_id: appointment.service_id,
          provider_id: appointment.provider_id,
          start_date: date,
          end_date: date,
        });
        const response = await fetch(`/api/availability/slots?${query}`);
        if (!response.ok) {
          throw new Error(
            await getMessage(response, "Unable to load available times."),
          );
        }
        const data: { slots: AvailabilitySlot[] } = await response.json();
        if (isCurrent) setSlots(data.slots);
      } catch (requestError) {
        if (isCurrent) {
          setSlots([]);
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load available times.",
          );
        }
      } finally {
        if (isCurrent) setIsLoading(false);
      }
    }
    void loadSlots();
    return () => {
      isCurrent = false;
    };
  }, [appointment.provider_id, appointment.service_id, date]);

  async function confirmReschedule() {
    if (!selectedSlot) return;
    setIsSubmitting(true);
    setError("");
    try {
      await rescheduleCustomerAppointment(
        token,
        appointment.id,
        selectedSlot.start,
      );
      await onComplete();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to reschedule this appointment.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="reschedule-flow">
      <div className="reschedule-flow__current">
        <span>Current appointment</span>
        <strong>{serviceName}</strong>
        <small>
          {formatDate(appointment.appointment_start)} at{" "}
          {formatTime(appointment.appointment_start)} with {providerName}
        </small>
      </div>
      {step === "date" ? (
        <>
          <label
            className="field-label"
            htmlFor={`reschedule-date-${appointment.id}`}
          >
            New date
            <input
              id={`reschedule-date-${appointment.id}`}
              min={getToday()}
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </label>
          {isLoading && (
            <p className="status-message">Loading available times...</p>
          )}
          {error && (
            <p className="status-message status-message--error" role="alert">
              {error}
            </p>
          )}
          {!isLoading && !error && slots.length === 0 && (
            <p className="status-message">No available times for this date.</p>
          )}
          {!isLoading && slots.length > 0 && (
            <div className="reschedule-slots" aria-label="Available times">
              {slots.map((slot) => (
                <button
                  className={
                    selectedSlot?.start === slot.start
                      ? "time-slot selected"
                      : "time-slot"
                  }
                  key={slot.start}
                  type="button"
                  onClick={() => setSelectedSlot(slot)}
                >
                  {formatTime(slot.start)}
                </button>
              ))}
            </div>
          )}
          <div className="appointment-actions">
            <button
              className="primary-button"
              type="button"
              disabled={!selectedSlot}
              onClick={() => setStep("confirm")}
            >
              Review new time
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={onCancel}
            >
              Keep current time
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="reschedule-confirmation">
            Move this appointment to{" "}
            <strong>{formatDate(selectedSlot!.start)}</strong> at{" "}
            <strong>{formatTime(selectedSlot!.start)}</strong> with the same
            provider, {providerName}?
          </p>
          {error && (
            <p className="status-message status-message--error" role="alert">
              {error}
            </p>
          )}
          <div className="appointment-actions">
            <button
              className="primary-button"
              type="button"
              disabled={isSubmitting}
              onClick={() => void confirmReschedule()}
            >
              {isSubmitting ? "Saving..." : "Confirm reschedule"}
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={isSubmitting}
              onClick={() => setStep("date")}
            >
              Choose another time
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default RescheduleFlow;
