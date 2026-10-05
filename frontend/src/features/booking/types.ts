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

export type BookingKind = "ONE_TIME" | "RECURRING";
export type RecurrenceAccess = "loading" | "customer" | "guest" | "unavailable";
export type RecurrenceFrequency = "WEEKLY" | "MONTHLY";
export type RecurrenceEndMode = "COUNT" | "END_DATE";
export type RecurrenceInterval = 1 | 2;

export type RecurrenceOptionsValue = {
  frequency: RecurrenceFrequency;
  interval: RecurrenceInterval;
  endMode: RecurrenceEndMode;
  occurrenceCount: number | null;
  endDate: string | null;
};

export type RecurrenceValidationErrors = Partial<
  Record<"frequency" | "occurrenceCount" | "endDate", string>
>;

export type RecurrenceValidation = {
  isValid: boolean;
  errors: RecurrenceValidationErrors;
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
  bookingKind: BookingKind;
  recurrence: RecurrenceOptionsValue;
  bookingMode: "self" | "other";
  details: BookingDetails;
};
