import { describe, expect, it } from "vitest";
import {
  generateRecurringOccurrences,
  RecurrenceGenerationError,
} from "./recurrence";
import { validateRecurrenceOptions } from "./utils";
import type { RecurrenceOptionsValue } from "./types";

function generate(
  overrides: Partial<Parameters<typeof generateRecurringOccurrences>[0]> = {},
) {
  return generateRecurringOccurrences({
    start_date: "2026-01-05",
    local_start_time: "10:30:00",
    frequency: "WEEKLY",
    interval: 1,
    end_mode: "COUNT",
    occurrence_count: 3,
    end_date: null,
    ...overrides,
  });
}

describe("generateRecurringOccurrences", () => {
  it("generates weekly COUNT occurrences", () => {
    expect(generate().map(({ date }) => date)).toEqual([
      "2026-01-05",
      "2026-01-12",
      "2026-01-19",
    ]);
  });

  it("generates biweekly COUNT occurrences", () => {
    expect(generate({ interval: 2 }).map(({ date }) => date)).toEqual([
      "2026-01-05",
      "2026-01-19",
      "2026-02-02",
    ]);
  });

  it("generates monthly COUNT occurrences", () => {
    expect(
      generate({
        start_date: "2026-01-15",
        frequency: "MONTHLY",
        interval: 1,
      }).map(({ date }) => date),
    ).toEqual(["2026-01-15", "2026-02-15", "2026-03-15"]);
  });

  it("clamps monthly dates to the month while preserving the original anchor", () => {
    expect(
      generate({
        start_date: "2026-01-31",
        frequency: "MONTHLY",
        interval: 1,
        occurrence_count: 5,
      }).map(({ date }) => date),
    ).toEqual([
      "2026-01-31",
      "2026-02-28",
      "2026-03-31",
      "2026-04-30",
      "2026-05-31",
    ]);
  });

  it("generates weekly END_DATE occurrences inclusively", () => {
    expect(
      generate({
        end_mode: "END_DATE",
        occurrence_count: null,
        end_date: "2026-01-19",
      }).map(({ date }) => date),
    ).toEqual(["2026-01-05", "2026-01-12", "2026-01-19"]);
  });

  it("accepts an END_DATE that generates exactly two occurrences", () => {
    expect(
      generate({
        end_mode: "END_DATE",
        occurrence_count: null,
        end_date: "2026-01-12",
      }),
    ).toHaveLength(2);
  });

  it("rejects an END_DATE that generates only one occurrence", () => {
    const result = validateRecurrenceOptions(
      {
        frequency: "WEEKLY",
        interval: 1,
        endMode: "END_DATE",
        occurrenceCount: null,
        endDate: "2026-01-11",
      },
      "2026-01-05",
    );

    expect(result).toEqual({
      isValid: false,
      errors: { endDate: "The end date must include at least 2 occurrences." },
    });
  });

  it("rejects COUNT = 1", () => {
    expect(() => generate({ occurrence_count: 1 })).toThrow(
      RecurrenceGenerationError,
    );
    expect(
      validateRecurrenceOptions(
        {
          frequency: "WEEKLY",
          interval: 1,
          endMode: "COUNT",
          occurrenceCount: 1,
          endDate: null,
        },
        "2026-01-05",
      ).errors.occurrenceCount,
    ).toBe("Choose between 2 and 52 occurrences.");
  });

  it("generates exactly 52 COUNT occurrences", () => {
    const occurrences = generate({ occurrence_count: 52 });

    expect(occurrences).toHaveLength(52);
    expect(occurrences[51].date).toBe("2026-12-28");
  });

  it("numbers occurrences sequentially and keeps dates chronological", () => {
    const occurrences = generate({
      start_date: "2026-01-31",
      frequency: "MONTHLY",
      interval: 1,
      occurrence_count: 5,
    });

    expect(occurrences.map(({ occurrenceNumber }) => occurrenceNumber)).toEqual(
      [1, 2, 3, 4, 5],
    );
    expect(occurrences.map(({ date }) => date)).toEqual([
      "2026-01-31",
      "2026-02-28",
      "2026-03-31",
      "2026-04-30",
      "2026-05-31",
    ]);
    expect(
      occurrences.every(({ localStartTime }) => localStartTime === "10:30:00"),
    ).toBe(true);
  });

  it("keeps END_DATE recurrence validation on the generator's calculated occurrences", () => {
    const value: RecurrenceOptionsValue = {
      frequency: "WEEKLY",
      interval: 2,
      endMode: "END_DATE",
      occurrenceCount: null,
      endDate: "2026-01-19",
    };

    expect(validateRecurrenceOptions(value, "2026-01-05").isValid).toBe(true);
  });
});
