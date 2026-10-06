import { useMemo } from "react";
import type { RecurrenceOptionsValue } from "../types";
import { validateRecurrenceOptions } from "../utils";

type Props = {
  value: RecurrenceOptionsValue;
  onChange: (value: RecurrenceOptionsValue) => void;
  startDate: string;
};

type FrequencyChoice = "weekly" | "biweekly" | "monthly";

function getFrequencyChoice(value: RecurrenceOptionsValue): FrequencyChoice {
  if (value.frequency === "MONTHLY") return "monthly";
  return value.interval === 2 ? "biweekly" : "weekly";
}

export default function RecurrenceOptions({
  value,
  onChange,
  startDate,
}: Props) {
  const validation = useMemo(
    () => validateRecurrenceOptions(value, startDate),
    [value, startDate],
  );

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
            min={2}
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
