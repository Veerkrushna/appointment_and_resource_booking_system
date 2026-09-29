export type CustomerAppointment = {
  id: string;
  service_id: string;
  provider_id: string;
  appointment_start: string;
  appointment_end: string;
  duration_minutes: number;
  status: string;
  notes: string | null;
};

export type CustomerAppointmentsResponse = {
  appointments: CustomerAppointment[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type NamedRecord = { id: string; name: string };

export type CustomerReview = {
  id: string;
  appointment_id: string;
  rating: number;
  comment: string | null;
  created_at: string;
  updated_at: string;
};

export type CustomerReviewInput = {
  rating: number;
  comment: string | null;
};

export const userTimeZone =
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export async function getMessage(response: Response, fallback: string) {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export async function fetchCustomerAppointments(token: string, page = 1) {
  const response = await fetch(
    `/api/customer/appointments?timezone=${encodeURIComponent(userTimeZone)}&page=${page}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );

  if (!response.ok) {
    throw new Error(await getMessage(response, "Unable to load appointments."));
  }

  const data: CustomerAppointmentsResponse = await response.json();

  return data;
}

export async function cancelCustomerAppointment(token: string, id: string) {
  const response = await fetch(`/api/customer/appointments/${id}/cancel`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      cancelled_by: "customer",
      reason: "Cancelled by customer",
    }),
  });
  if (!response.ok) {
    throw new Error(
      await getMessage(response, "Unable to cancel this appointment."),
    );
  }
}

export async function rescheduleCustomerAppointment(
  token: string,
  id: string,
  appointmentStart: string,
) {
  const response = await fetch(
    `/api/customer/appointments/${id}/reschedule?timezone=${encodeURIComponent(userTimeZone)}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        appointment_start: appointmentStart,
        cancelled_by: "customer",
        reason: "Rescheduled by customer",
      }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await getMessage(response, "Unable to reschedule this appointment."),
    );
  }
}
export type CustomerProfile = {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  role: string;
  is_active: boolean;
};

export async function updateCustomerProfile(
  token: string,
  profile: {
    name: string;
    email: string;
    phone: string | null;
  },
) {
  const response = await fetch("/api/auth/me", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(profile),
  });

  if (!response.ok) {
    throw new Error(
      await getMessage(response, "Unable to update your profile."),
    );
  }

  const data: CustomerProfile = await response.json();

  return data;
}

function reviewErrorMessage(status: number, operation: "load" | "save") {
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 403) return "You are not allowed to access this review.";
  if (status === 404) return "The appointment or review could not be found.";
  if (status === 409) {
    return "This appointment already has a review. Refresh your appointments.";
  }
  if (status === 422) {
    return "Please check your rating and try submitting again.";
  }
  return operation === "load"
    ? "Unable to load this review. Please try again."
    : "Unable to submit your review. Please try again.";
}

async function requestCustomerReview(
  token: string,
  path: string,
  operation: "load" | "save",
  method = "GET",
  payload?: object,
): Promise<CustomerReview | null> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(payload ? { "Content-Type": "application/json" } : {}),
      },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    });
  } catch {
    throw new Error(
      operation === "load"
        ? "Unable to load this review. Please try again."
        : "Unable to submit your review. Please try again.",
    );
  }

  if (operation === "load" && response.status === 404) return null;
  if (!response.ok) {
    throw new Error(reviewErrorMessage(response.status, operation));
  }

  try {
    return (await response.json()) as CustomerReview;
  } catch {
    throw new Error(
      operation === "load"
        ? "Unable to load this review. Please try again."
        : "Unable to submit your review. Please try again.",
    );
  }
}

export async function fetchAppointmentReview(
  token: string,
  appointmentId: string,
) {
  return requestCustomerReview(
    token,
    `/api/reviews/appointment/${appointmentId}`,
    "load",
  );
}

export async function createAppointmentReview(
  token: string,
  appointmentId: string,
  input: CustomerReviewInput,
) {
  const review = await requestCustomerReview(
    token,
    "/api/reviews",
    "save",
    "POST",
    { appointment_id: appointmentId, ...input },
  );
  if (!review)
    throw new Error("Unable to submit your review. Please try again.");
  return review;
}

export async function updateAppointmentReview(
  token: string,
  reviewId: string,
  input: CustomerReviewInput,
) {
  const review = await requestCustomerReview(
    token,
    `/api/reviews/${reviewId}`,
    "save",
    "PUT",
    input,
  );
  if (!review)
    throw new Error("Unable to submit your review. Please try again.");
  return review;
}
