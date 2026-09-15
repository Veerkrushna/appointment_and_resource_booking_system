import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

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
};

type AvailabilityResponse = {
  slots: AvailabilitySlot[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

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

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

function BookingPage() {
  const { serviceId } = useParams();
  const [searchParams] = useSearchParams();
  const initialDate = searchParams.get("date") || "";
  const providerId = searchParams.get("providerId") || "";
  const [service, setService] = useState<Service | null>(null);
  const [date, setDate] = useState(initialDate);
  const [availableSlots, setAvailableSlots] = useState<AvailabilitySlot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<AvailabilitySlot | null>(
    null,
  );
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [availabilityError, setAvailabilityError] = useState<string | null>(
    null,
  );
  const [step, setStep] = useState(1);
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [details, setDetails] = useState<BookingDetails>({
    name: "",
    email: "",
    phone: "",
    notes: "",
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

    if (!date || !serviceId) {
      return () => {
        isCurrent = false;
      };
    }

    const selectedServiceId = serviceId;

    async function loadAvailability() {
      setAvailabilityLoading(true);
      setAvailabilityError(null);
      setAvailableSlots([]);
      setSelectedSlot(null);

      const query = new URLSearchParams({
        service_id: selectedServiceId,
        start_date: date,
        end_date: date,
      });
      if (providerId) {
        query.set("provider_id", providerId);
      }

      try {
        const response = await fetch(
          `/api/availability/slots?${query.toString()}`,
        );
        if (!response.ok) {
          throw new Error("Unable to load available times.");
        }

        const data: AvailabilityResponse = await response.json();
        if (isCurrent) {
          setAvailableSlots(data.slots);
        }
      } catch (requestError) {
        if (isCurrent) {
          setAvailabilityError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load available times.",
          );
        }
      } finally {
        if (isCurrent) {
          setAvailabilityLoading(false);
        }
      }
    }

    void loadAvailability();

    return () => {
      isCurrent = false;
    };
  }, [date, providerId, serviceId]);

  const steps = useMemo(
    () => ["Date & time", "Your details", "Confirmation"],
    [],
  );

  function handleDetailsChange(field: keyof BookingDetails, value: string) {
    setDetails((current) => ({ ...current, [field]: value }));
  }

  function submitDetails(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStep(3);
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
                        No available times for this date.
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
            <form onSubmit={submitDetails}>
              <p className="panel-kicker">Step 2 of 3</p>
              <h2>Tell us about you</h2>
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
                <strong>{details.name}</strong>
                <span>{details.email}</span>
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
                    onClick={() => setIsConfirmed(true)}
                    type="button"
                  >
                    Confirm booking <span aria-hidden="true">&#8594;</span>
                  </button>
                </div>
              )}
              <small className="booking-note">
                This confirmation is currently a frontend preview until
                appointment availability and booking endpoints are enabled.
              </small>
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
