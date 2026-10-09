import { useEffect, useMemo, useRef, useState } from "react";
import { formatInTimeZone } from "date-fns-tz";
import type { FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import type {
  Service,
  BookingDetails,
  AvailabilitySlot,
  ProviderOption,
  ProviderType,
  BookingDraft,
  BookingKind,
  RecurrenceAccess,
  RecurrenceOptionsValue,
} from "../features/booking/types";
import { generateRecurringOccurrences } from "../features/booking/recurrence";
import {
  BOOKING_DRAFT_STORAGE_KEY,
  readBookingDraft,
  draftMatchesCurrentBooking,
  fetchAvailabilitySlots,
  getProviderOptions,
  isValidEmail,
  createDefaultRecurrenceOptions,
  validateRecurrenceOptions,
} from "../features/booking/utils";
import {
  AppointmentSeriesApiError,
  createAppointmentSeries,
} from "../lib/appointmentSeries";
import type { AppointmentSeriesResponse } from "../lib/appointmentSeries";
import {
  PaymentApiError,
  createPaymentOrder,
  verifyPayment,
} from "../lib/payments";
import type { PaymentOrderResponse } from "../lib/payments";
import { openRazorpayCheckout } from "../lib/razorpayCheckout";
import type { CheckoutResult } from "../lib/razorpayCheckout";
import BookingSummary from "../features/booking/components/BookingSummary";
import BookingSteps from "../features/booking/components/BookingSteps";
import StepDateTime from "../features/booking/components/StepDateTime";
import StepDetails from "../features/booking/components/StepDetails";
import StepConfirmation from "../features/booking/components/StepConfirmation";
import type { PaymentFlowState } from "../features/booking/components/StepConfirmation";

function BookingPage() {
  const { token, customer, isLoading: authIsLoading } = useAuth();
  const { serviceId } = useParams();
  const [searchParams] = useSearchParams();
  const initialDate = searchParams.get("date") || "";
  const providerId = searchParams.get("providerId") || "";
  const hasAuthenticatedCustomer = Boolean(customer);

  const initialDraft = readBookingDraft();
  const initialBookingState: {
    bookingMode: "self" | "other";
    bookingKind: BookingKind;
    recurrence: RecurrenceOptionsValue;
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
        bookingKind: "ONE_TIME",
        recurrence: createDefaultRecurrenceOptions(),
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
      bookingKind: restoredDraft.bookingKind,
      recurrence: restoredDraft.recurrence,
      date: restoredDraft.date || initialDate,
      selectedSlot: restoredDraft.selectedSlot,
      details: restoredDraft.details,
      step: restoredDraft.step,
    };
  })();

  const [bookingMode, setBookingMode] = useState<"self" | "other">(
    initialBookingState.bookingMode,
  );
  const [bookingKind, setBookingKind] = useState<BookingKind>(
    initialBookingState.bookingKind,
  );
  const [recurrence, setRecurrence] = useState<RecurrenceOptionsValue>(
    initialBookingState.recurrence,
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
  const [providerTimezones, setProviderTimezones] = useState<
    Record<string, string>
  >({});
  const [providerTimezonesLoaded, setProviderTimezonesLoaded] = useState(false);
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
  const [recurringSeries, setRecurringSeries] =
    useState<AppointmentSeriesResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const bookingSubmissionInFlight = useRef(false);
  const [details, setDetails] = useState<BookingDetails>(
    initialBookingState.details,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [bookingOutcomeUnknown, setBookingOutcomeUnknown] = useState(false);
  const [paymentFlowState, setPaymentFlowState] =
    useState<PaymentFlowState>("ready");
  const [activePaymentOrder, setActivePaymentOrder] = useState<{
    order: PaymentOrderResponse;
    requestKey: string;
  } | null>(null);
  const [step, setStep] = useState(initialBookingState.step);
  const recurrenceStartDate = selectedSlot?.date || date;
  const recurrenceValidation = useMemo(
    () => validateRecurrenceOptions(recurrence, recurrenceStartDate),
    [recurrence, recurrenceStartDate],
  );
  const recurrenceAccess: RecurrenceAccess = authIsLoading
    ? "loading"
    : customer?.role.toLowerCase() === "customer"
      ? "customer"
      : customer
        ? "unavailable"
        : "guest";
  const timezoneProviderId = selectedSlot?.provider_id || selectedProviderId;
  const selectedProviderTimezone = timezoneProviderId
    ? (providerTimezones[timezoneProviderId] ?? null)
    : null;
  const recurrenceOccurrences = useMemo(() => {
    if (
      step !== 3 ||
      bookingKind !== "RECURRING" ||
      !recurrenceValidation.isValid ||
      !selectedSlot ||
      !selectedProviderTimezone
    ) {
      return [];
    }

    return generateRecurringOccurrences({
      start_date: selectedSlot.date,
      local_start_time: formatInTimeZone(
        selectedSlot.start,
        selectedProviderTimezone,
        "HH:mm:ss",
      ),
      frequency: recurrence.frequency,
      interval: recurrence.interval,
      end_mode: recurrence.endMode,
      occurrence_count:
        recurrence.endMode === "COUNT" ? recurrence.occurrenceCount : null,
      end_date: recurrence.endMode === "END_DATE" ? recurrence.endDate : null,
    });
  }, [
    bookingKind,
    recurrence,
    recurrenceValidation.isValid,
    selectedProviderTimezone,
    selectedSlot,
    step,
  ]);

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
        return response.json() as Promise<
          { id: string; type: string; timezone?: string | null }[]
        >;
      })
      .then((providers) => {
        if (!isCurrent) return;
        const types: Record<string, ProviderType> = {};
        const timezones: Record<string, string> = {};
        for (const provider of providers) {
          const type = provider.type.toLowerCase();
          if (type === "person" || type === "resource") {
            types[provider.id] = type;
          }
          if (provider.timezone) {
            timezones[provider.id] = provider.timezone;
          }
        }
        setProviderTypes(types);
        setProviderTimezones(timezones);
      })
      .catch(() => {
        // Provider types are supplemental; availability remains usable without them.
      })
      .finally(() => {
        if (isCurrent) setProviderTimezonesLoaded(true);
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
      bookingKind,
      recurrence,
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
    bookingKind,
    bookingMode,
    date,
    details,
    recurrence,
    selectedProviderId,
    selectedSlot,
    serviceId,
    step,
  ]);

  function handleDetailsChange(field: keyof BookingDetails, value: string) {
    setDetails((current) => ({ ...current, [field]: value }));
  }

  function handleBookingKindChange(kind: BookingKind) {
    setBookingKind(kind);
  }

  function handleRecurrenceChange(value: RecurrenceOptionsValue) {
    setRecurrence(value);
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
    if (bookingKind === "RECURRING" && !recurrenceValidation.isValid) {
      setBookingError("Complete the recurrence options before continuing.");
      return;
    }
    if (!isValidEmail(details.email)) {
      setBookingError("Not a valid email. Kindly check Again");
      return;
    }
    setBookingError(null);
    setStep(3);
  }

  async function confirmRecurringBooking() {
    if (bookingSubmissionInFlight.current || isConfirmed) return;

    if (authIsLoading) {
      setBookingError("Checking your account. Please try again in a moment.");
      return;
    }
    if (!token || !customer || customer.role.toLowerCase() !== "customer") {
      setBookingError(
        "Sign in with a customer account to book recurring appointments.",
      );
      return;
    }
    if (!selectedSlot || !service) {
      setBookingError("Choose an available time before continuing.");
      return;
    }
    if (!recurrenceValidation.isValid) {
      setBookingError("Complete the recurrence options before continuing.");
      return;
    }
    if (!selectedProviderTimezone) {
      setBookingError("The provider timezone is not available yet.");
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
    let requestSent = false;

    try {
      const request = {
        service_id: service.id,
        provider_id: selectedSlot.provider_id,
        start_date: selectedSlot.date,
        local_start_time: formatInTimeZone(
          selectedSlot.start,
          selectedProviderTimezone,
          "HH:mm:ss",
        ),
        frequency: recurrence.frequency,
        interval: recurrence.interval,
        end_mode: recurrence.endMode,
        occurrence_count:
          recurrence.endMode === "COUNT" ? recurrence.occurrenceCount : null,
        end_date: recurrence.endMode === "END_DATE" ? recurrence.endDate : null,
        user_name: details.name,
        user_email: details.email,
        user_phone: details.phone || null,
        notes: details.notes || null,
      };

      requestSent = true;
      const createdSeries = await createAppointmentSeries(token, request);
      window.sessionStorage.removeItem(BOOKING_DRAFT_STORAGE_KEY);
      setRecurringSeries(createdSeries);
      setIsConfirmed(true);
    } catch (requestError) {
      const outcomeUnknown =
        requestSent &&
        (!(requestError instanceof AppointmentSeriesApiError) ||
          requestError.status === null ||
          requestError.status >= 500);
      setBookingOutcomeUnknown(outcomeUnknown);

      if (requestError instanceof AppointmentSeriesApiError) {
        if (requestError.status === 409) {
          const conflictDetails = requestError.conflicts
            .map(
              (conflict) =>
                `Occurrence ${conflict.occurrence_number} on ${conflict.date}: ${conflict.reason}`,
            )
            .join(" ");
          setBookingError(
            conflictDetails
              ? `One of the recurring appointments is unavailable. ${conflictDetails}`
              : "One of the recurring appointments is unavailable. Review the recurrence and try again.",
          );
        } else {
          setBookingError(requestError.message);
        }
      } else if (outcomeUnknown) {
        setBookingError(
          "We couldn't confirm whether your recurring bookings were created. Check My Appointments before trying again.",
        );
      } else {
        setBookingError(
          "Unable to prepare the recurring booking. Check the selected provider and try again.",
        );
      }
    } finally {
      bookingSubmissionInFlight.current = false;
      setIsSubmitting(false);
    }
  }

  async function confirmBooking() {
    if (bookingKind === "RECURRING") {
      await confirmRecurringBooking();
      return;
    }

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

    if (authIsLoading) {
      setBookingError("Checking your account. Please try again in a moment.");
      return;
    }
    if (!token || !customer || customer.role.toLowerCase() !== "customer") {
      setBookingError(
        "Sign in with a customer account to make a paid booking.",
      );
      return;
    }

    bookingSubmissionInFlight.current = true;
    setIsSubmitting(true);
    setBookingError(null);
    setBookingOutcomeUnknown(false);
    let verificationAttempted = false;
    try {
      const paymentRequest = {
        service_id: service.id,
        provider_id: selectedSlot.provider_id,
        appointment_start: selectedSlot.start,
        user_name: details.name,
        user_email: details.email,
        user_phone: details.phone || null,
        notes: details.notes || null,
      };
      const requestKey = JSON.stringify(paymentRequest);
      let order =
        activePaymentOrder?.requestKey === requestKey &&
        new Date(activePaymentOrder.order.hold_expires_at).getTime() >
          Date.now()
          ? activePaymentOrder.order
          : null;

      if (!order) {
        setPaymentFlowState("creating-order");
        order = await createPaymentOrder(token, paymentRequest);
        setActivePaymentOrder({ order, requestKey });
      }

      setPaymentFlowState("loading-checkout");
      let checkoutResult: CheckoutResult;
      try {
        checkoutResult = await openRazorpayCheckout(
          order,
          service.name,
          selectedSlot.provider_name,
          details.name,
          details.email,
          details.phone,
        );
      } catch {
        setPaymentFlowState("failed");
        setBookingError(
          "Razorpay Checkout couldn't be opened. Your slot is temporarily held and will be released automatically if you don't complete payment. You can retry payment using this order or leave the page.",
        );
        return;
      }

      if (checkoutResult.kind === "dismissed") {
        setPaymentFlowState("dismissed");
        setBookingError(
          "Payment was not completed. Your slot is temporarily held and will be released automatically if you don't complete payment.",
        );
        return;
      }
      if (checkoutResult.kind === "failed") {
        setPaymentFlowState("failed");
        setBookingError(
          "Razorpay reported that the payment was not completed. Your slot may remain temporarily held until the hold expires.",
        );
        return;
      }
      setPaymentFlowState("verifying");
      verificationAttempted = true;
      await verifyPayment(token, {
        payment_id: order.payment_id,
        order_id: checkoutResult.response.razorpay_order_id,
        provider_payment_id: checkoutResult.response.razorpay_payment_id,
        signature: checkoutResult.response.razorpay_signature,
      });

      window.sessionStorage.removeItem(BOOKING_DRAFT_STORAGE_KEY);
      setPaymentFlowState("confirmed");
      setActivePaymentOrder(null);
      setIsConfirmed(true);
      setAvailableSlots((current) =>
        current.filter(
          (slot) =>
            slot.start !== selectedSlot.start ||
            slot.provider_id !== selectedSlot.provider_id,
        ),
      );
    } catch (requestError) {
      const outcomeUnknown = verificationAttempted
        ? !(
            requestError instanceof PaymentApiError &&
            (requestError.status === 400 || requestError.status === 422)
          )
        : requestError instanceof PaymentApiError &&
          (requestError.status === null || requestError.status >= 500);
      setBookingOutcomeUnknown(outcomeUnknown);
      setPaymentFlowState(
        outcomeUnknown
          ? verificationAttempted
            ? "unknown"
            : "order-unknown"
          : "failed",
      );
      setBookingError(
        requestError instanceof PaymentApiError
          ? requestError.message
          : "Unable to start payment. Please review the booking and try again.",
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
          bookingKind={bookingKind}
          recurrence={recurrence}
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
              bookingKind={bookingKind}
              setBookingKind={handleBookingKindChange}
              recurrence={recurrence}
              setRecurrence={handleRecurrenceChange}
              recurrenceValidation={recurrenceValidation}
              recurrenceAccess={recurrenceAccess}
              selectedProviderTimezone={selectedProviderTimezone}
              providerTimezonesLoaded={providerTimezonesLoaded}
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
              bookingKind={bookingKind}
              details={details}
              selectedSlot={selectedSlot}
              service={service}
              date={date}
              setStep={setStep}
              isSubmitting={isSubmitting}
              bookingOutcomeUnknown={bookingOutcomeUnknown}
              paymentFlowState={paymentFlowState}
              recurringSeries={recurringSeries}
              recurrenceValidation={recurrenceValidation}
              recurrenceOccurrences={recurrenceOccurrences}
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
