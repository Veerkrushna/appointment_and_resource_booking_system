import type {
  AvailabilitySlot,
  BookingDraft,
  AvailabilityResponse,
  ProviderOption,
  RecurrenceValidation,
  RecurrenceValidationErrors,
  RecurrenceOptionsValue,
} from "./types";
import {
  generateRecurringOccurrences,
  RecurrenceGenerationError,
} from "./recurrence";

export const BOOKING_DRAFT_STORAGE_KEY = "booking-page-draft";

export function createDefaultRecurrenceOptions(): RecurrenceOptionsValue {
  return {
    frequency: "WEEKLY",
    interval: 1,
    endMode: "COUNT",
    occurrenceCount: 2,
    endDate: null,
  };
}

export function validateRecurrenceOptions(
  value: RecurrenceOptionsValue,
  startDate: string,
): RecurrenceValidation {
  const errors: RecurrenceValidationErrors = {};

  if (value.endMode === "END_DATE" && !startDate) {
    errors.endDate = "Choose a start date first.";
    return { isValid: false, errors };
  }

  try {
    generateRecurringOccurrences({
      start_date: startDate || "2000-01-01",
      local_start_time: "00:00:00",
      frequency: value.frequency,
      interval: value.interval,
      end_mode: value.endMode,
      occurrence_count:
        value.endMode === "COUNT" ? value.occurrenceCount : null,
      end_date: value.endMode === "END_DATE" ? value.endDate : null,
    });
  } catch (error) {
    if (error instanceof RecurrenceGenerationError) {
      if (error.field === "frequency") {
        errors.frequency = error.message;
      } else if (error.field === "occurrenceCount") {
        errors.occurrenceCount = error.message;
      } else {
        errors.endDate = error.message;
      }
    } else {
      throw error;
    }
  }

  return { isValid: Object.keys(errors).length === 0, errors };
}

function normalizeRecurrenceOptions(value: unknown): RecurrenceOptionsValue {
  if (typeof value !== "object" || value === null) {
    return createDefaultRecurrenceOptions();
  }

  const saved = value as Partial<RecurrenceOptionsValue>;
  const frequency = saved.frequency === "MONTHLY" ? "MONTHLY" : "WEEKLY";
  const endMode = saved.endMode === "END_DATE" ? "END_DATE" : "COUNT";

  return {
    frequency,
    interval: frequency === "MONTHLY" ? 1 : saved.interval === 2 ? 2 : 1,
    endMode,
    occurrenceCount:
      endMode === "COUNT"
        ? typeof saved.occurrenceCount === "number"
          ? saved.occurrenceCount
          : saved.occurrenceCount === null
            ? null
            : 2
        : null,
    endDate:
      endMode === "END_DATE" && typeof saved.endDate === "string"
        ? saved.endDate
        : null,
  };
}

export function normalizeBookingValue(value: string | null | undefined) {
  return value == null ? "" : value.trim();
}

export function slotMatchesCurrentContext(
  slot: AvailabilitySlot | null,
  serviceId: string | undefined,
  providerId: string,
  date: string,
) {
  if (!slot || !serviceId) {
    return false;
  }

  if (slot.service_id !== serviceId || slot.date !== date) {
    return false;
  }

  if (providerId) {
    return slot.provider_id === providerId;
  }

  return true;
}

export function readBookingDraft(): BookingDraft | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const rawDraft = window.sessionStorage.getItem(BOOKING_DRAFT_STORAGE_KEY);
    if (!rawDraft) {
      return null;
    }

    const draft = JSON.parse(rawDraft) as Partial<BookingDraft>;
    if (
      typeof draft !== "object" ||
      draft === null ||
      typeof draft.step !== "number" ||
      typeof draft.date !== "string" ||
      !draft.details ||
      (draft.bookingMode !== "self" && draft.bookingMode !== "other")
    ) {
      window.sessionStorage.removeItem(BOOKING_DRAFT_STORAGE_KEY);
      return null;
    }

    return {
      serviceId: typeof draft.serviceId === "string" ? draft.serviceId : null,
      providerId:
        typeof draft.providerId === "string" ? draft.providerId : null,
      bookingKind: draft.bookingKind === "RECURRING" ? "RECURRING" : "ONE_TIME",
      recurrence: normalizeRecurrenceOptions(draft.recurrence),
      step: draft.step,
      date: draft.date,
      selectedSlot: draft.selectedSlot ?? null,
      bookingMode: draft.bookingMode,
      details: {
        name: typeof draft.details.name === "string" ? draft.details.name : "",
        email:
          typeof draft.details.email === "string" ? draft.details.email : "",
        phone:
          typeof draft.details.phone === "string" ? draft.details.phone : "",
        notes:
          typeof draft.details.notes === "string" ? draft.details.notes : "",
      },
    };
  } catch {
    window.sessionStorage.removeItem(BOOKING_DRAFT_STORAGE_KEY);
    return null;
  }
}

export function draftMatchesCurrentBooking(
  draft: BookingDraft | null,
  serviceId: string | undefined,
  providerId: string,
  date: string,
) {
  if (!draft || !serviceId || draft.serviceId !== serviceId) {
    return false;
  }

  const activeProviderId = normalizeBookingValue(providerId);
  const savedProviderId = normalizeBookingValue(draft.providerId);

  if (
    activeProviderId &&
    savedProviderId &&
    activeProviderId !== savedProviderId
  ) {
    return false;
  }

  const activeDate = normalizeBookingValue(date);
  const savedDate = normalizeBookingValue(draft.date);

  if (activeDate && savedDate && activeDate !== savedDate) {
    return false;
  }

  return true;
}

export function formatDate(date: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${date}T12:00:00`));
}

export function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export async function fetchAvailabilitySlots(
  serviceId: string,
  date: string,
  providerId?: string,
) {
  const query = new URLSearchParams({
    service_id: serviceId,
    start_date: date,
    end_date: date,
  });
  if (providerId) query.set("provider_id", providerId);

  const response = await fetch(`/api/availability/slots?${query.toString()}`);
  if (!response.ok) {
    throw new Error("Unable to load available times.");
  }

  const data: AvailabilityResponse = await response.json();
  return data.slots;
}

export function getProviderOptions(
  slots: AvailabilitySlot[],
): ProviderOption[] {
  const providers = new Map<string, ProviderOption>();
  for (const slot of slots) {
    if (!providers.has(slot.provider_id)) {
      providers.set(slot.provider_id, {
        id: slot.provider_id,
        name: slot.provider_name,
        averageRating: slot.provider_average_rating ?? null,
        ratingCount: slot.provider_rating_count ?? 0,
      });
    }
  }
  return [...providers.values()].sort((left, right) =>
    left.name.localeCompare(right.name),
  );
}

export function getToday() {
  return new Date().toISOString().slice(0, 10);
}

export function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}
