export type Service = {
  id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  price: string | number | null;
  category: string;
  status: "active" | "inactive";
};

export type BookingDetails = {
  name: string;
  email: string;
  phone: string;
  notes: string;
};

export type AvailabilitySlot = {
  provider_id: string;
  provider_name: string;
  service_id: string;
  date: string;
  start: string;
  end: string;
  duration_minutes: number;
  provider_average_rating?: number | null;
  provider_rating_count?: number;
};

export type AvailabilityResponse = {
  slots: AvailabilitySlot[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type ProviderOption = {
  id: string;
  name: string;
  averageRating: number | null;
  ratingCount: number;
};

export type ProviderType = "person" | "resource";

export type BookingDraft = {
  serviceId: string | null;
  providerId: string | null;
  step: number;
  date: string;
  selectedSlot: AvailabilitySlot | null;
  bookingMode: "self" | "other";
  details: BookingDetails;
};
