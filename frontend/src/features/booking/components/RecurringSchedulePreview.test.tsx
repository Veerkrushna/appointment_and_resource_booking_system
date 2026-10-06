import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RecurringSchedulePreview from "./RecurringSchedulePreview";
import type { RecurringOccurrence } from "../recurrence";

const occurrences: RecurringOccurrence[] = [
  {
    occurrenceNumber: 1,
    date: "2026-10-06",
    localStartTime: "10:55:00",
  },
  {
    occurrenceNumber: 2,
    date: "2026-10-13",
    localStartTime: "10:55:00",
  },
];

describe("RecurringSchedulePreview", () => {
  it("renders each supplied occurrence number, provider-local date, and time", () => {
    const markup = renderToStaticMarkup(
      createElement(RecurringSchedulePreview, {
        bookingKind: "RECURRING",
        occurrences,
      }),
    );

    expect(markup).toContain("Recurring schedule · 2 appointments");
    expect(markup).toContain("#1");
    expect(markup).toContain("Tue, October 6, 2026");
    expect(markup).toContain("10:55 AM");
    expect(markup).toContain("#2");
    expect(markup).toContain("Tue, October 13, 2026");
    expect(markup.match(/recurring-schedule__item/g)).toHaveLength(2);
  });

  it("does not render a schedule for one-time bookings", () => {
    const markup = renderToStaticMarkup(
      createElement(RecurringSchedulePreview, {
        bookingKind: "ONE_TIME",
        occurrences,
      }),
    );

    expect(markup).toBe("");
  });
});
