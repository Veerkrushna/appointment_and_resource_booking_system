import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import {
  Service,
  BookingDetails,
  AvailabilitySlot,
  ProviderOption,
  ProviderType,
  BookingDraft,
} from "../features/booking/types";
import {
  BOOKING_DRAFT_STORAGE_KEY,
  readBookingDraft,
  draftMatchesCurrentBooking,
  fetchAvailabilitySlots,
  getProviderOptions,
  isValidEmail,
} from "../features/booking/utils";
import BookingSummary from "../features/booking/components/BookingSummary";
import BookingSteps from "../features/booking/components/BookingSteps";
import StepDateTime from "../features/booking/components/StepDateTime";
import StepDetails from "../features/booking/components/StepDetails";
import StepConfirmation from "../features/booking/components/StepConfirmation";

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
        if (
          currentSlot &&
          !slots.some(
            (slot) =>
              slot.service_id === selectedServiceId &&
              slot.provider_id === currentSlot.provider_id &&
              slot.date === selectedDate &&
              slot.start === currentSlot.start,
          )
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

      <BookingSteps steps={steps} currentStep={step} />

      <div className="booking-layout">
        <BookingSummary
          service={service}
          selectedSlot={selectedSlot}
          date={date}
        />

        <div className="booking-panel">
          {step === 1 && (
            <StepDateTime
              date={date}
              setDate={setDate}
              selectedSlot={selectedSlot}
              setSelectedSlot={setSelectedSlot}
              availableSlots={availableSlots}
              providerOptions={providerOptions}
              providerTypes={providerTypes}
              selectedProviderId={selectedProviderId}
              handleProviderChange={handleProviderChange}
              availabilityLoading={availabilityLoading}
              availabilityError={availabilityError}
              setAvailableSlots={setAvailableSlots}
              setAvailabilityError={setAvailabilityError}
              setAvailabilityLoading={setAvailabilityLoading}
              setStep={setStep}
            />
          )}

          {step === 2 && (
            <StepDetails
              hasAuthenticatedCustomer={hasAuthenticatedCustomer}
              bookingMode={bookingMode}
              applyBookingMode={applyBookingMode}
              details={details}
              handleDetailsChange={handleDetailsChange}
              submitDetails={submitDetails}
              bookingError={bookingError}
              setStep={setStep}
            />
          )}

          {step === 3 && (
            <StepConfirmation
              isConfirmed={isConfirmed}
              details={details}
              selectedSlot={selectedSlot}
              service={service}
              date={date}
              setStep={setStep}
              isSubmitting={isSubmitting}
              bookingOutcomeUnknown={bookingOutcomeUnknown}
              confirmBooking={confirmBooking}
              bookingError={bookingError}
            />
          )}
        </div>
      </div>
    </section>
  );
}

export default BookingPage;
