import type { RecurrenceEndMode, RecurrenceFrequency } from "./types";

export const MAX_RECURRENCE_OCCURRENCES = 52;
const MIN_RECURRENCE_OCCURRENCES = 2;

export type RecurringOccurrence = {
  occurrenceNumber: number;
  date: string;
  localStartTime: string;
};

export type RecurrenceGenerationInput = {
  start_date: string;
  local_start_time: string;
  frequency: RecurrenceFrequency;
  interval: number;
  end_mode: RecurrenceEndMode;
  occurrence_count: number | null;
  end_date: string | null;
};

export type RecurrenceErrorField = "frequency" | "occurrenceCount" | "endDate";

export class RecurrenceGenerationError extends Error {
  readonly field: RecurrenceErrorField;

  constructor(message: string, field: RecurrenceErrorField) {
    super(message);
    this.name = "RecurrenceGenerationError";
    this.field = field;
  }
}

type CalendarDate = {
  year: number;
  month: number;
  day: number;
};

function parseDate(
  value: string,
  field: "start_date" | "end_date",
): CalendarDate {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    throw new RecurrenceGenerationError(
      `${field} must be a valid date.`,
      field === "start_date" ? "endDate" : "endDate",
    );
  }

  const [, yearPart, monthPart, dayPart] = match;
  const year = Number(yearPart);
  const month = Number(monthPart);
  const day = Number(dayPart);
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth(year, month)
  ) {
    throw new RecurrenceGenerationError(
      `${field} must be a valid date.`,
      "endDate",
    );
  }
  return { year, month, day };
}

function daysInMonth(year: number, month: number): number {
  if (month === 2) {
    const isLeapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return isLeapYear ? 29 : 28;
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

function formatDate({ year, month, day }: CalendarDate): string {
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function addWeeks(startDate: CalendarDate, weeks: number): CalendarDate {
  const date = new Date(0);
  date.setUTCHours(0, 0, 0, 0);
  date.setUTCFullYear(
    startDate.year,
    startDate.month - 1,
    startDate.day + weeks * 7,
  );
  const result = {
    year: date.getUTCFullYear(),
    month: date.getUTCMonth() + 1,
    day: date.getUTCDate(),
  };
  if (result.year < 1 || result.year > 9999) {
    throw new RecurrenceGenerationError(
      "Generated occurrence date is out of range.",
      "endDate",
    );
  }
  return result;
}

function monthlyOccurrenceDate(
  startDate: CalendarDate,
  occurrenceIndex: number,
): CalendarDate {
  const monthIndex =
    startDate.year * 12 + startDate.month - 1 + occurrenceIndex;
  const year = Math.floor(monthIndex / 12);
  if (year < 1 || year > 9999) {
    throw new RecurrenceGenerationError(
      "Generated occurrence date is out of range.",
      "endDate",
    );
  }
  const month = (monthIndex % 12) + 1;
  return {
    year,
    month,
    day: Math.min(startDate.day, daysInMonth(year, month)),
  };
}

function validateLocalStartTime(value: string): void {
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(value)) {
    throw new RecurrenceGenerationError(
      "local_start_time must be a valid local time.",
      "frequency",
    );
  }
}

/** Generates provider-local calendar dates; final timezone and DST checks are backend-owned. */
export function generateRecurringOccurrences({
  start_date,
  local_start_time,
  frequency,
  interval,
  end_mode,
  occurrence_count,
  end_date,
}: RecurrenceGenerationInput): RecurringOccurrence[] {
  const anchorDate = parseDate(start_date, "start_date");
  validateLocalStartTime(local_start_time);

  if (
    (frequency === "WEEKLY" && interval !== 1 && interval !== 2) ||
    (frequency === "MONTHLY" && interval !== 1)
  ) {
    throw new RecurrenceGenerationError(
      "Choose a supported recurrence frequency.",
      "frequency",
    );
  }
  if (frequency !== "WEEKLY" && frequency !== "MONTHLY") {
    throw new RecurrenceGenerationError(
      "Choose a supported recurrence frequency.",
      "frequency",
    );
  }

  let endDate: CalendarDate | null = null;
  if (end_mode === "COUNT") {
    if (
      occurrence_count == null ||
      !Number.isInteger(occurrence_count) ||
      occurrence_count < MIN_RECURRENCE_OCCURRENCES ||
      occurrence_count > MAX_RECURRENCE_OCCURRENCES
    ) {
      throw new RecurrenceGenerationError(
        `Choose between ${MIN_RECURRENCE_OCCURRENCES} and ${MAX_RECURRENCE_OCCURRENCES} occurrences.`,
        "occurrenceCount",
      );
    }
    if (end_date !== null) {
      throw new RecurrenceGenerationError(
        "COUNT end mode cannot include an end date.",
        "occurrenceCount",
      );
    }
  } else if (end_mode === "END_DATE") {
    if (!end_date) {
      throw new RecurrenceGenerationError("Choose an end date.", "endDate");
    }
    if (occurrence_count !== null) {
      throw new RecurrenceGenerationError(
        "END_DATE end mode cannot include an occurrence count.",
        "endDate",
      );
    }
    endDate = parseDate(end_date, "end_date");
    if (formatDate(endDate) < formatDate(anchorDate)) {
      throw new RecurrenceGenerationError(
        "End date cannot be before the start date.",
        "endDate",
      );
    }
  } else {
    throw new RecurrenceGenerationError(
      "Choose a supported recurrence end mode.",
      "endDate",
    );
  }

  const occurrences: RecurringOccurrence[] = [];
  let occurrenceIndex = 0;

  while (true) {
    if (end_mode === "COUNT" && occurrenceIndex >= occurrence_count!) {
      return occurrences;
    }

    const occurrenceDate =
      frequency === "WEEKLY"
        ? addWeeks(anchorDate, interval * occurrenceIndex)
        : monthlyOccurrenceDate(anchorDate, occurrenceIndex);

    if (endDate && formatDate(occurrenceDate) > formatDate(endDate)) {
      if (occurrences.length < MIN_RECURRENCE_OCCURRENCES) {
        throw new RecurrenceGenerationError(
          "The end date must include at least 2 occurrences.",
          "endDate",
        );
      }
      return occurrences;
    }
    if (occurrences.length >= MAX_RECURRENCE_OCCURRENCES) {
      throw new RecurrenceGenerationError(
        `Recurrence cannot exceed ${MAX_RECURRENCE_OCCURRENCES} occurrences.`,
        "endDate",
      );
    }

    occurrences.push({
      occurrenceNumber: occurrences.length + 1,
      date: formatDate(occurrenceDate),
      localStartTime: local_start_time,
    });
    occurrenceIndex += 1;
  }
}
