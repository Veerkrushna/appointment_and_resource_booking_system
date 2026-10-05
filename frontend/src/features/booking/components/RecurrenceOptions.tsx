import { useEffect, useMemo, useRef } from "react";
import type {
  RecurrenceOptionsValue,
  RecurrenceValidation,
  RecurrenceValidationErrors,
} from "../types";

type Props = {
  value: RecurrenceOptionsValue;
  onChange: (value: RecurrenceOptionsValue) => void;
  startDate: string;
  onValidationChange?: (validation: RecurrenceValidation) => void;
};

type FrequencyChoice = "weekly" | "biweekly" | "monthly";

function getFrequencyChoice(value: RecurrenceOptionsValue): FrequencyChoice {
  if (value.frequency === "MONTHLY") return "monthly";
  return value.interval === 2 ? "biweekly" : "weekly";
}

function validate(
  value: RecurrenceOptionsValue,
  startDate: string,
): RecurrenceValidation {
  const errors: RecurrenceValidationErrors = {};

  if (
    (value.frequency === "WEEKLY" &&
      value.interval !== 1 &&
      value.interval !== 2) ||
    (value.frequency === "MONTHLY" && value.interval !== 1)
  ) {
    errors.frequency = "Choose a supported recurrence frequency.";
  }

  if (value.endMode === "COUNT") {
    if (value.occurrenceCount == null) {
      errors.occurrenceCount = "Enter the number of occurrences.";
    } else if (!Number.isInteger(value.occurrenceCount)) {
      errors.occurrenceCount = "Enter a whole number of occurrences.";
    } else if (value.occurrenceCount < 1 || value.occurrenceCount > 52) {
      errors.occurrenceCount = "Choose between 1 and 52 occurrences.";
    }
  } else if (!value.endDate) {
    errors.endDate = "Choose an end date.";
  } else if (!startDate) {
    errors.endDate = "Choose a start date first.";
  } else if (value.endDate < startDate) {
    errors.endDate = "End date cannot be before the start date.";
  }

  return { isValid: Object.keys(errors).length === 0, errors };
}

export default function RecurrenceOptions({
  value,
  onChange,
  startDate,
  onValidationChange,
}: Props) {
  const validation = useMemo(
    () => validate(value, startDate),
    [value, startDate],
  );
  const validationCallback = useRef(onValidationChange);

  useEffect(() => {
    validationCallback.current = onValidationChange;
  }, [onValidationChange]);

  useEffect(() => {
    validationCallback.current?.(validation);
  }, [validation]);

  function changeFrequency(choice: FrequencyChoice) {
    if (choice === "monthly") {
      onChange({ ...value, frequency: "MONTHLY", interval: 1 });
    } else {
      onChange({
        ...value,
        frequency: "WEEKLY",
        interval: choice === "biweekly" ? 2 : 1,
      });
    }
  }

  function changeEndMode(endMode: RecurrenceOptionsValue["endMode"]) {
    onChange({
      ...value,
      endMode,
      occurrenceCount: endMode === "COUNT" ? value.occurrenceCount : null,
      endDate: endMode === "END_DATE" ? value.endDate : null,
    });
  }

  const frequencyChoice = getFrequencyChoice(value);
  const frequencyErrorId = "recurrence-frequency-error";
  const countErrorId = "recurrence-count-error";
  const endDateErrorId = "recurrence-end-date-error";

  return (
    <section
      className="recurrence-options"
      aria-labelledby="recurrence-heading"
    >
      <h3 id="recurrence-heading">Repeat this appointment</h3>

      <div
        className="booking-mode-toggle"
        role="radiogroup"
        aria-label="Recurrence frequency"
        aria-describedby={
          validation.errors.frequency ? frequencyErrorId : undefined
        }
      >
        <label
          className={`booking-mode-option ${frequencyChoice === "weekly" ? "selected" : ""}`}
        >
          <input
            checked={frequencyChoice === "weekly"}
            name="recurrence-frequency"
            onChange={() => changeFrequency("weekly")}
            type="radio"
          />
          <span className="booking-mode-copy">
            <span className="booking-mode-title">Weekly</span>
          </span>
        </label>
        <label
          className={`booking-mode-option ${frequencyChoice === "biweekly" ? "selected" : ""}`}
        >
          <input
            checked={frequencyChoice === "biweekly"}
            name="recurrence-frequency"
            onChange={() => changeFrequency("biweekly")}
            type="radio"
          />
          <span className="booking-mode-copy">
            <span className="booking-mode-title">Every 2 weeks</span>
          </span>
        </label>
        <label
          className={`booking-mode-option ${frequencyChoice === "monthly" ? "selected" : ""}`}
        >
          <input
            checked={frequencyChoice === "monthly"}
            name="recurrence-frequency"
            onChange={() => changeFrequency("monthly")}
            type="radio"
          />
          <span className="booking-mode-copy">
            <span className="booking-mode-title">Monthly</span>
          </span>
        </label>
      </div>
      {validation.errors.frequency && (
        <p
          className="status-message status-message--error"
          id={frequencyErrorId}
          role="alert"
        >
          {validation.errors.frequency}
        </p>
      )}

      <div
        className="booking-mode-toggle"
        role="radiogroup"
        aria-label="When the series ends"
      >
        <label
          className={`booking-mode-option ${value.endMode === "COUNT" ? "selected" : ""}`}
        >
          <input
            checked={value.endMode === "COUNT"}
            name="recurrence-end-mode"
            onChange={() => changeEndMode("COUNT")}
            type="radio"
          />
          <span className="booking-mode-copy">
            <span className="booking-mode-title">After a number of visits</span>
          </span>
        </label>
        <label
          className={`booking-mode-option ${value.endMode === "END_DATE" ? "selected" : ""}`}
        >
          <input
            checked={value.endMode === "END_DATE"}
            name="recurrence-end-mode"
            onChange={() => changeEndMode("END_DATE")}
            type="radio"
          />
          <span className="booking-mode-copy">
            <span className="booking-mode-title">On a date</span>
          </span>
        </label>
      </div>

      {value.endMode === "COUNT" ? (
        <label className="field-label" htmlFor="recurrence-count">
          Number of occurrences
          <input
            id="recurrence-count"
            type="number"
            min={1}
            max={52}
            step={1}
            required
            value={value.occurrenceCount ?? ""}
            aria-invalid={Boolean(validation.errors.occurrenceCount)}
            aria-describedby={
              validation.errors.occurrenceCount ? countErrorId : undefined
            }
            onChange={(event) => {
              const rawValue = event.currentTarget.value;
              onChange({
                ...value,
                endMode: "COUNT",
                occurrenceCount: rawValue === "" ? null : Number(rawValue),
                endDate: null,
              });
            }}
          />
          {validation.errors.occurrenceCount && (
            <span
              className="status-message status-message--error"
              id={countErrorId}
            >
              {validation.errors.occurrenceCount}
            </span>
          )}
        </label>
      ) : (
        <label className="field-label" htmlFor="recurrence-end-date">
          End date
          <input
            id="recurrence-end-date"
            type="date"
            min={startDate || undefined}
            required
            disabled={!startDate}
            value={value.endDate ?? ""}
            aria-invalid={Boolean(validation.errors.endDate)}
            aria-describedby={
              validation.errors.endDate ? endDateErrorId : undefined
            }
            onChange={(event) =>
              onChange({
                ...value,
                endMode: "END_DATE",
                occurrenceCount: null,
                endDate: event.currentTarget.value || null,
              })
            }
          />
          {validation.errors.endDate && (
            <span
              className="status-message status-message--error"
              id={endDateErrorId}
            >
              {validation.errors.endDate}
            </span>
          )}
        </label>
      )}
    </section>
  );
}
