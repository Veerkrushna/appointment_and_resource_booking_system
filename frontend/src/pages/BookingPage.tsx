import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import ProviderRatingSelect from "../components/ProviderRatingSelect";

type Service = {
  id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  price: string | number | null;
  category: string;
  status: "active" | "inactive";
};

type BookingDetails = {
  name: string;
  email: string;
  phone: string;
  notes: string;
};

type AvailabilitySlot = {
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

type AvailabilityResponse = {
  slots: AvailabilitySlot[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

type ProviderOption = {
  id: string;
  name: string;
  averageRating: number | null;
  ratingCount: number;
};

type ProviderType = "person" | "resource";

type BookingDraft = {
  serviceId: string | null;
  providerId: string | null;
  step: number;
  date: string;
  selectedSlot: AvailabilitySlot | null;
  bookingMode: "self" | "other";
  details: BookingDetails;
};

const BOOKING_DRAFT_STORAGE_KEY = "booking-page-draft";

function normalizeBookingValue(value: string | null | undefined) {
  return value == null ? "" : value.trim();
}

function slotMatchesCurrentContext(
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

function readBookingDraft(): BookingDraft | null {
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

function draftMatchesCurrentBooking(
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

function formatDate(date: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${date}T12:00:00`));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

async function fetchAvailabilitySlots(
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

function getProviderOptions(slots: AvailabilitySlot[]): ProviderOption[] {
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

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function BookingPage() {
  const { token, customer } = useAuth();
  const { serviceId } = useParams();
  const [searchParams] = useSearchParams();
  const initialDate = searchParams.get("date") || "";
  const providerId = searchParams.get("providerId") || "";
  const hasAuthenticatedCustomer = Boolean(customer);

  const initialDraft = readBookingDraft();
  const initialBookingState: {
    bookingMode: "self" | "other";
    date: string;
    selectedSlot: AvailabilitySlot | null;
    details: BookingDetails;
    step: number;
  } = (() => {
    const restoredDraft = draftMatchesCurrentBooking(
      initialDraft,
      serviceId,
      providerId,
      initialDate,
    )
      ? initialDraft
      : null;

    if (!restoredDraft) {
      return {
        bookingMode: hasAuthenticatedCustomer ? "self" : "other",
        date: initialDate,
        selectedSlot: null,
        details: hasAuthenticatedCustomer
          ? {
              name: customer?.name ?? "",
              email: customer?.email ?? "",
              phone: customer?.phone ?? "",
              notes: "",
            }
          : {
              name: "",
              email: "",
              phone: "",
              notes: "",
            },
        step: 1,
      };
    }

    return {
      bookingMode: restoredDraft.bookingMode,
      date: restoredDraft.date || initialDate,
      selectedSlot: restoredDraft.selectedSlot,
      details: restoredDraft.details,
      step: restoredDraft.step,
    };
  })();

  const [bookingMode, setBookingMode] = useState<"self" | "other">(
    initialBookingState.bookingMode,
  );
  const [service, setService] = useState<Service | null>(null);
  const [date, setDate] = useState(initialBookingState.date);
  const [availableSlots, setAvailableSlots] = useState<AvailabilitySlot[]>([]);
  const [allAvailableSlots, setAllAvailableSlots] = useState<
    AvailabilitySlot[]
  >([]);
  const [providerOptions, setProviderOptions] = useState<ProviderOption[]>([]);
  const [providerTypes, setProviderTypes] = useState<
    Record<string, ProviderType>
  >({});
  const [selectedProviderId, setSelectedProviderId] = useState(providerId);
  const selectedProviderIdRef = useRef(providerId);
  const selectedSlotRef = useRef(initialBookingState.selectedSlot);
  const availabilityRequestId = useRef(0);
  const [selectedSlot, setSelectedSlot] = useState<AvailabilitySlot | null>(
    initialBookingState.selectedSlot,
  );
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [availabilityError, setAvailabilityError] = useState<string | null>(
    null,
  );
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const bookingSubmissionInFlight = useRef(false);
  const [details, setDetails] = useState<BookingDetails>(
    initialBookingState.details,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [bookingOutcomeUnknown, setBookingOutcomeUnknown] = useState(false);
  const [step, setStep] = useState(initialBookingState.step);

  useEffect(() => {
    let isCurrent = true;

    async function loadService() {
      try {
        const response = await fetch(`/api/services/${serviceId}`);
        if (!response.ok) {
          throw new Error("Service not found.");
        }

        const data: Service = await response.json();
        if (isCurrent) {
          if (data.status !== "active") {
            setError("This service is no longer available for booking.");
          } else {
            setService(data);
          }
        }
      } catch (requestError) {
        if (isCurrent) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load this service.",
          );
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    void loadService();

    return () => {
      isCurrent = false;
    };
  }, [serviceId]);

  useEffect(() => {
    let isCurrent = true;
    fetch("/api/providers")
      .then((response) => {
        if (!response.ok) return [];
        return response.json() as Promise<{ id: string; type: string }[]>;
      })
      .then((providers) => {
        if (!isCurrent) return;
        const types: Record<string, ProviderType> = {};
        for (const provider of providers) {
          const type = provider.type.toLowerCase();
          if (type === "person" || type === "resource") {
            types[provider.id] = type;
          }
        }
        setProviderTypes(types);
      })
      .catch(() => {
        // Provider types are supplemental; availability remains usable without them.
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  useEffect(() => {
    selectedSlotRef.current = selectedSlot;
  }, [selectedSlot]);

  useEffect(() => {
    let isCurrent = true;
    const requestId = ++availabilityRequestId.current;

    if (!date || !serviceId) {
      return () => {
        isCurrent = false;
      };
    }
    const selectedServiceId = serviceId;
    const selectedDate = date;

    async function loadAvailability() {
      setAvailabilityLoading(true);
      setAvailabilityError(null);
      setAvailableSlots([]);
      setAllAvailableSlots([]);
      setProviderOptions([]);
      let allSlotsLoaded = false;

      try {
        const allSlots = await fetchAvailabilitySlots(
          selectedServiceId,
          selectedDate,
        );
        if (!isCurrent || requestId !== availabilityRequestId.current) return;

        allSlotsLoaded = true;
        setAllAvailableSlots(allSlots);
        const options = getProviderOptions(allSlots);
        setProviderOptions(options);

        const requestedProviderId = selectedProviderIdRef.current;
        let slots = allSlots;
        if (requestedProviderId) {
          if (options.some((provider) => provider.id === requestedProviderId)) {
            slots = await fetchAvailabilitySlots(
              selectedServiceId,
              selectedDate,
              requestedProviderId,
            );
          } else {
            selectedProviderIdRef.current = "";
            setSelectedProviderId("");
          }
        }

        if (!isCurrent || requestId !== availabilityRequestId.current) return;
        setAvailableSlots(slots);

        const currentSlot = selectedSlotRef.current;
        const slotMatchesContext = slotMatchesCurrentContext(
          currentSlot,
          selectedServiceId,
          requestedProviderId,
          selectedDate,
        );
        if (
          currentSlot &&
          (!slotMatchesContext ||
            !slots.some(
              (slot) =>
                slot.service_id === selectedServiceId &&
                slot.provider_id === currentSlot.provider_id &&
                slot.date === selectedDate &&
                slot.start === currentSlot.start,
            ))
        ) {
          selectedSlotRef.current = null;
          setSelectedSlot(null);
          setBookingError(
            "The previously selected time is no longer available. Please choose another one.",
          );
          setStep(1);
        }
      } catch {
        if (isCurrent && requestId === availabilityRequestId.current) {
          if (!allSlotsLoaded) {
            selectedProviderIdRef.current = "";
            setSelectedProviderId("");
            setAllAvailableSlots([]);
            setProviderOptions([]);
          }
          setAvailabilityError("Unable to load available times.");
        }
      } finally {
        if (isCurrent && requestId === availabilityRequestId.current) {
          setAvailabilityLoading(false);
        }
      }
    }

    void loadAvailability();

    return () => {
      isCurrent = false;
    };
  }, [date, serviceId]);

  function handleProviderChange(nextProviderId: string) {
    selectedProviderIdRef.current = nextProviderId;
    setSelectedProviderId(nextProviderId);
    selectedSlotRef.current = null;
    setSelectedSlot(null);
    setBookingError(null);

    const requestId = ++availabilityRequestId.current;
    if (!nextProviderId) {
      setAvailabilityError(null);
      setAvailableSlots(allAvailableSlots);
      setAvailabilityLoading(false);
      return;
    }

    if (!date || !serviceId) return;

    setAvailabilityLoading(true);
    setAvailabilityError(null);
    void fetchAvailabilitySlots(serviceId, date, nextProviderId)
      .then((slots) => {
        if (requestId === availabilityRequestId.current) {
          setAvailableSlots(slots);
        }
      })
      .catch(() => {
        if (requestId === availabilityRequestId.current) {
          setAvailableSlots([]);
          setAvailabilityError("Unable to load available times.");
        }
      })
      .finally(() => {
        if (requestId === availabilityRequestId.current) {
          setAvailabilityLoading(false);
        }
      });
  }

  const steps = useMemo(
    () => ["Date & time", "Your details", "Confirmation"],
    [],
  );

  useEffect(() => {
    if (!serviceId) {
      window.sessionStorage.removeItem(BOOKING_DRAFT_STORAGE_KEY);
      return;
    }

    const draft: BookingDraft = {
      serviceId,
      providerId: selectedProviderId || selectedSlot?.provider_id || null,
      step,
      date,
      selectedSlot,
      bookingMode,
      details,
    };

    window.sessionStorage.setItem(
      BOOKING_DRAFT_STORAGE_KEY,
      JSON.stringify(draft),
    );
  }, [
    bookingMode,
    date,
    details,
    selectedProviderId,
    selectedSlot,
    serviceId,
    step,
  ]);

  function handleDetailsChange(field: keyof BookingDetails, value: string) {
    setDetails((current) => ({ ...current, [field]: value }));
  }

  function applyBookingMode(mode: "self" | "other") {
    setBookingMode(mode);

    if (!customer) {
      return;
    }

    if (mode === "self") {
      setDetails((current) => ({
        ...current,
        name: customer.name,
        email: customer.email,
        phone: customer.phone ?? "",
      }));
      return;
    }

    setDetails((current) => ({
      ...current,
      name: "",
      email: "",
      phone: "",
    }));
  }

  function submitDetails(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isValidEmail(details.email)) {
      setBookingError("Not a valid email. Kindly check Again");
      return;
    }
    setBookingError(null);
    setStep(3);
  }

  async function confirmBooking() {
    if (
      !selectedSlot ||
      !service ||
      bookingSubmissionInFlight.current ||
      isConfirmed
    ) {
      return;
    }

    if (new Date(selectedSlot.start).getTime() <= Date.now()) {
      setAvailableSlots((current) =>
        current.filter((slot) => new Date(slot.start).getTime() > Date.now()),
      );
      setSelectedSlot(null);
      setStep(1);
      setBookingError(
        "That time has already passed. Choose another available time.",
      );
      return;
    }

    bookingSubmissionInFlight.current = true;
    setIsSubmitting(true);
    setBookingError(null);
    setBookingOutcomeUnknown(false);
    let responseReceived = false;
    let responseStatus = 0;
    try {
      const response = await fetch("/api/appointments", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          service_id: service.id,
          provider_id: selectedSlot.provider_id,
          user_name: details.name,
          user_email: details.email,
          user_phone: details.phone || null,
          appointment_start: selectedSlot.start,
          notes: details.notes || null,
        }),
      });
      responseReceived = true;
      responseStatus = response.status;

      if (!response.ok) {
        let message = "Unable to confirm this booking.";
        try {
          const body = await response.json();
          if (typeof body.detail === "string") {
            message = body.detail;
          }
        } catch {
          // Keep the fallback for non-JSON error responses.
        }
        throw new Error(message);
      }

      window.sessionStorage.removeItem(BOOKING_DRAFT_STORAGE_KEY);
      setIsConfirmed(true);
      setAvailableSlots((current) =>
        current.filter(
          (slot) =>
            slot.start !== selectedSlot.start ||
            slot.provider_id !== selectedSlot.provider_id,
        ),
      );
    } catch (requestError) {
      const outcomeUnknown = !responseReceived || responseStatus >= 500;
      setBookingOutcomeUnknown(outcomeUnknown);
      setBookingError(
        outcomeUnknown
          ? "We couldn't confirm whether your booking was created. Check My Appointments before trying again."
          : requestError instanceof Error
            ? requestError.message
            : "Unable to confirm this booking.",
      );
    } finally {
      bookingSubmissionInFlight.current = false;
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <p className="status-message booking-status">
        Loading booking details...
      </p>
    );
  }

  if (error || !service) {
    return (
      <div
        className="status-message status-message--error booking-status"
        role="alert"
      >
        <strong>We could not open this booking.</strong>
        <span>{error || "Service not found."}</span>
        <Link to="/services">Return to services</Link>
      </div>
    );
  }

  return (
    <section className="booking-page">
      <Link className="back-link" to="/services">
        &#8592; Back to services
      </Link>
      <div className="booking-header">
        <div>
          <p className="eyebrow">Reserve your time</p>
          <h1>Book {service.name}</h1>
          <p className="services-intro">
            Choose a time that works for you, then share your details to finish.
          </p>
        </div>
        <span className="booking-category">{service.category}</span>
      </div>

      <div className="booking-steps" aria-label="Booking progress">
        {steps.map((label, index) => {
          const stepNumber = index + 1;
          return (
            <div
              className={
                step >= stepNumber ? "booking-step active" : "booking-step"
              }
              key={label}
            >
              <span>{stepNumber}</span>
              <small>{label}</small>
            </div>
          );
        })}
      </div>

      <div className="booking-layout">
        <aside className="booking-summary">
          <p className="summary-label">Your selection</p>
          <h2>{service.name}</h2>
          <p>
            {service.description ||
              "Appointment details will be confirmed with your provider."}
          </p>
          <dl>
            <div>
              <dt>Provider</dt>
              <dd>{selectedSlot?.provider_name || "Not selected"}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{service.duration_minutes} min</dd>
            </div>
            <div>
              <dt>Date</dt>
              <dd>{date ? formatDate(date) : "Not selected"}</dd>
            </div>
            <div>
              <dt>Time</dt>
              <dd>
                {selectedSlot ? formatTime(selectedSlot.start) : "Not selected"}
              </dd>
            </div>
          </dl>
        </aside>

        <div className="booking-panel">
          {step === 1 && (
            <div>
              <p className="panel-kicker">Step 1 of 3</p>
              <h2>Select a date and time</h2>
              <label className="field-label" htmlFor="booking-date">
                Preferred date
              </label>
              <input
                className="date-input"
                id="booking-date"
                min={getToday()}
                onChange={(event) => {
                  const nextDate = event.target.value;
                  if (nextDate !== date && selectedSlot) {
                    setSelectedSlot(null);
                  }
                  setDate(nextDate);
                  if (!nextDate) {
                    setAvailableSlots([]);
                    setSelectedSlot(null);
                    setAvailabilityError(null);
                    setAvailabilityLoading(false);
                  }
                }}
                type="date"
                value={date}
              />

              {date && (
                <div className="time-selection">
                  <div className="time-selection__heading">
                    <span>Available times</span>
                    <small>{formatDate(date)}</small>
                  </div>
                  <ProviderRatingSelect
                    providers={providerOptions}
                    providerTypes={providerTypes}
                    selectedProviderId={selectedProviderId}
                    disabled={availabilityLoading}
                    onChange={handleProviderChange}
                  />
                  {availabilityLoading && (
                    <p className="status-message">Loading available times...</p>
                  )}
                  {availabilityError && (
                    <p
                      className="status-message status-message--error"
                      role="alert"
                    >
                      {availabilityError}
                    </p>
                  )}
                  {!availabilityLoading &&
                    !availabilityError &&
                    availableSlots.length === 0 && (
                      <p className="status-message">
                        {selectedProviderId
                          ? `No available appointments for ${providerOptions.find((provider) => provider.id === selectedProviderId)?.name ?? "this provider"} on this date.`
                          : "No available times for this date."}
                      </p>
                    )}
                  {!availabilityLoading &&
                    !availabilityError &&
                    availableSlots.length > 0 && (
                      <div className="time-grid">
                        {availableSlots.map((slot) => (
                          <button
                            className={
                              selectedSlot?.start === slot.start &&
                              selectedSlot.provider_id === slot.provider_id
                                ? "time-button active"
                                : "time-button"
                            }
                            key={`${slot.provider_id}-${slot.start}`}
                            onClick={() => setSelectedSlot(slot)}
                            type="button"
                          >
                            <span>{formatTime(slot.start)}</span>
                            <small>{slot.provider_name}</small>
                          </button>
                        ))}
                      </div>
                    )}
                </div>
              )}

              <button
                className="primary-button"
                disabled={!date || !selectedSlot}
                onClick={() => setStep(2)}
                type="button"
              >
                Continue to details <span aria-hidden="true">&#8594;</span>
              </button>
            </div>
          )}

          {step === 2 && (
            <form noValidate onSubmit={submitDetails}>
              <p className="panel-kicker">Step 2 of 3</p>
              <h2>Who is this appointment for?</h2>

              {hasAuthenticatedCustomer && (
                <div
                  className="booking-mode-toggle"
                  role="radiogroup"
                  aria-label="Appointment booking recipient"
                >
                  <label
                    className={`booking-mode-option ${bookingMode === "self" ? "selected" : ""}`}
                  >
                    <input
                      checked={bookingMode === "self"}
                      onChange={() => applyBookingMode("self")}
                      type="radio"
                    />
                    <span className="booking-mode-copy">
                      <span className="booking-mode-title">
                        Book for myself
                      </span>
                      <span className="booking-mode-description">
                        Use my account details
                      </span>
                    </span>
                  </label>
                  <label
                    className={`booking-mode-option ${bookingMode === "other" ? "selected" : ""}`}
                  >
                    <input
                      checked={bookingMode === "other"}
                      onChange={() => applyBookingMode("other")}
                      type="radio"
                    />
                    <span className="booking-mode-copy">
                      <span className="booking-mode-title">
                        Book for someone else
                      </span>
                      <span className="booking-mode-description">
                        Enter their contact details
                      </span>
                    </span>
                  </label>
                </div>
              )}

              <div className="form-grid">
                <label className="field-label">
                  Full name
                  <input
                    required
                    onChange={(event) =>
                      handleDetailsChange("name", event.target.value)
                    }
                    type="text"
                    value={details.name}
                  />
                </label>
                <label className="field-label">
                  Email address
                  <input
                    required
                    aria-describedby="booking-email-error"
                    onChange={(event) =>
                      handleDetailsChange("email", event.target.value)
                    }
                    type="email"
                    value={details.email}
                  />
                </label>
                <label className="field-label">
                  Phone number <span>(optional)</span>
                  <input
                    onChange={(event) =>
                      handleDetailsChange("phone", event.target.value)
                    }
                    type="tel"
                    value={details.phone}
                  />
                </label>
                <label className="field-label">
                  Notes <span>(optional)</span>
                  <textarea
                    onChange={(event) =>
                      handleDetailsChange("notes", event.target.value)
                    }
                    rows={4}
                    value={details.notes}
                  />
                </label>
              </div>
              {bookingError && (
                <p
                  className="status-message status-message--error"
                  id="booking-email-error"
                  role="alert"
                >
                  {bookingError}
                </p>
              )}
              <div className="booking-actions">
                <button
                  className="secondary-button"
                  onClick={() => setStep(1)}
                  type="button"
                >
                  Back
                </button>
                <button className="primary-button" type="submit">
                  Review booking <span aria-hidden="true">&#8594;</span>
                </button>
              </div>
            </form>
          )}

          {step === 3 && (
            <div className="confirmation-panel">
              <span className="confirmation-mark" aria-hidden="true">
                &#10003;
              </span>
              <p className="panel-kicker">Step 3 of 3</p>
              <h2>
                {isConfirmed
                  ? "Booking request received"
                  : "Review your booking"}
              </h2>
              <p>
                {isConfirmed
                  ? "Your appointment details are ready to be processed. We will follow up at the email address below."
                  : "Everything looks good. Confirm the details below to request this appointment."}
              </p>
              <div className="confirmation-details">
                <strong>
                  {isConfirmed ? "Booked for" : "Appointment for"}:{" "}
                  {details.name}
                </strong>
                <span>{details.email}</span>
                <span>
                  Provider: {selectedSlot?.provider_name || "Not selected"}
                </span>
                <span>Service: {service.name}</span>
                <span>
                  {formatDate(date)} at{" "}
                  {selectedSlot
                    ? formatTime(selectedSlot.start)
                    : "Not selected"}
                </span>
              </div>
              {!isConfirmed && (
                <div className="booking-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setStep(2)}
                    type="button"
                  >
                    Edit details
                  </button>
                  <button
                    className="primary-button"
                    disabled={isSubmitting || bookingOutcomeUnknown}
                    onClick={() => void confirmBooking()}
                    type="button"
                  >
                    {isSubmitting ? "Saving booking..." : "Confirm booking"}{" "}
                    <span aria-hidden="true">&#8594;</span>
                  </button>
                </div>
              )}
              {bookingOutcomeUnknown && (
                <Link className="service-book-link" to="/appointments">
                  Check My Appointments
                </Link>
              )}
              {bookingError && (
                <p
                  className="status-message status-message--error"
                  role="alert"
                >
                  {bookingError}
                </p>
              )}
              {isConfirmed && (
                <Link className="service-book-link" to="/appointments">
                  View appointments <span aria-hidden="true">&#8594;</span>
                </Link>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export default BookingPage;
