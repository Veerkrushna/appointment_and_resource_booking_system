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
