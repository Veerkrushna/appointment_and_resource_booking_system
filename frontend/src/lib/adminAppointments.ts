export type AdminAppointment = {
  id: string;
  service_id: string;
  provider_id: string;
  user_name: string;
  user_email: string;
  user_phone: string | null;
  appointment_start: string;
  appointment_end: string;
  duration_minutes: number;
  notes: string | null;
  status: string;
  provider_name: string;
  service_name: string;
};

export type AdminAppointmentListResponse = {
  appointments: AdminAppointment[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type AdminAppointmentFilters = {
  timezone?: string;
  provider_id?: string;
  service_id?: string;
  status?: string;
  search?: string;
  provider_search?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
};

export async function fetchAdminAppointments(
  token: string,
  filters: AdminAppointmentFilters = {},
): Promise<AdminAppointmentListResponse> {
  const params = new URLSearchParams();

  params.set(
    "timezone",
    filters.timezone ||
      Intl.DateTimeFormat().resolvedOptions().timeZone ||
      "UTC",
  );

  if (filters.provider_id) {
    params.set("provider_id", filters.provider_id);
  }

  if (filters.service_id) {
    params.set("service_id", filters.service_id);
  }

  if (filters.status) {
    params.set("status", filters.status);
  }

  if (filters.search?.trim()) {
    params.set("search", filters.search.trim());
  }

  if (filters.provider_search?.trim()) {
    params.set("provider_search", filters.provider_search.trim());
  }

  if (filters.start_date) {
    params.set("start_date", filters.start_date);
  }

  if (filters.end_date) {
    params.set("end_date", filters.end_date);
  }

  params.set("page", String(filters.page ?? 1));

  const response = await fetch(`/api/admin/appointments?${params}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Failed to fetch admin appointments");
  }

  return response.json();
}
