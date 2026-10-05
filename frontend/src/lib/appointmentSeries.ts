import type {
  RecurrenceEndMode,
  RecurrenceFrequency,
  RecurrenceInterval,
} from "../features/booking/types";

export type AppointmentSeriesCreateRequest = {
  service_id: string;
  provider_id: string;
  start_date: string;
  local_start_time: string;
  frequency: RecurrenceFrequency;
  interval: RecurrenceInterval;
  end_mode: RecurrenceEndMode;
  occurrence_count: number | null;
  end_date: string | null;
  user_name: string;
  user_email: string;
  user_phone: string | null;
  notes: string | null;
};

export type AppointmentSeriesConflict = {
  occurrence_number: number;
  date: string;
  reason: string;
};

export type AppointmentSeriesOccurrence = {
  id: string;
  occurrence_number: number;
  appointment_start: string;
  appointment_end: string;
  status: "confirmed" | "completed" | "cancelled";
};

export type AppointmentSeriesResponse = {
  id: string;
  service_id: string;
  provider_id: string;
  frequency: "weekly" | "monthly";
  interval: RecurrenceInterval;
  start_date: string;
  local_start_time: string;
  timezone: string;
  end_mode: "count" | "end_date";
  occurrence_count: number | null;
  end_date: string | null;
  status: "active" | "cancelled";
  occurrences: AppointmentSeriesOccurrence[];
};

export class AppointmentSeriesApiError extends Error {
  readonly status: number | null;
  readonly conflicts: AppointmentSeriesConflict[];

  constructor(
    message: string,
    status: number | null,
    conflicts: AppointmentSeriesConflict[] = [],
  ) {
    super(message);
    this.name = "AppointmentSeriesApiError";
    this.status = status;
    this.conflicts = conflicts;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseConflicts(value: unknown): AppointmentSeriesConflict[] {
  if (!Array.isArray(value)) return [];

  return value.filter(
    (conflict): conflict is AppointmentSeriesConflict =>
      isRecord(conflict) &&
      typeof conflict.occurrence_number === "number" &&
      typeof conflict.date === "string" &&
      typeof conflict.reason === "string",
  );
}

function errorMessage(status: number, detail: unknown): string {
  if (status >= 500) {
    return "We couldn't create your recurring appointments. Please try again.";
  }
  if (status === 401) {
    return "Your session has expired. Please sign in again.";
  }
  if (status === 403) {
    return "Recurring booking is available to customer accounts only.";
  }
  if (status === 409) {
    return isRecord(detail) && typeof detail.message === "string"
      ? detail.message
      : "One or more recurring appointments are unavailable.";
  }
  if (status === 422) {
    return "Please check your recurrence settings and contact details.";
  }
  if (typeof detail === "string") return detail;
  return "Unable to create recurring appointments. Please try again.";
}

export async function createAppointmentSeries(
  token: string,
  request: AppointmentSeriesCreateRequest,
): Promise<AppointmentSeriesResponse> {
  let response: Response;
  try {
    response = await fetch("/api/appointment-series", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(request),
    });
  } catch {
    throw new AppointmentSeriesApiError(
      "Unable to reach the server. Check your appointments before trying again.",
      null,
    );
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    if (response.ok) {
      throw new AppointmentSeriesApiError(
        "The recurring booking response could not be read. Check your appointments before trying again.",
        null,
      );
    }
  }

  if (!response.ok) {
    const detail = isRecord(body) ? body.detail : undefined;
    const conflicts =
      response.status === 409 && isRecord(detail)
        ? parseConflicts(detail.conflicts)
        : [];
    throw new AppointmentSeriesApiError(
      errorMessage(response.status, detail),
      response.status,
      conflicts,
    );
  }

  return body as AppointmentSeriesResponse;
}
