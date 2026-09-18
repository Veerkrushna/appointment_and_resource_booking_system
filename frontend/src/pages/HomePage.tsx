import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import CustomerHomePage from "./CustomerHomePage";

type Service = {
  id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  price: string | number | null;
  category: string;
  status: string;
};

type Provider = {
  id: string;
  name: string;
  type: "person" | "resource";
  availability_status: "available" | "on_leave" | "inactive";
};

type AvailabilityResponse = {
  slots: Array<{
    provider_id: string;
    provider_name: string;
    service_id: string;
    date: string;
    start: string;
    end: string;
    duration_minutes: number;
  }>;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

const providerTones = ["coral", "sage", "gold"];

function formatPrice(price: Service["price"]) {
  return price === null
    ? "Price on request"
    : `₹${Number(price).toLocaleString("en-IN")}`;
}

function getInitials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

function PublicHomePage() {
  const [serviceId, setServiceId] = useState("");
  const [providerId, setProviderId] = useState("");
  const [date, setDate] = useState("");
  const [services, setServices] = useState<Service[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [servicesLoading, setServicesLoading] = useState(true);
  const [providersLoading, setProvidersLoading] = useState(true);
  const [servicesError, setServicesError] = useState("");
  const [providersError, setProvidersError] = useState("");
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [availabilityError, setAvailabilityError] = useState("");
  const [availabilityResult, setAvailabilityResult] =
    useState<AvailabilityResponse | null>(null);

  useEffect(() => {
    let isCurrent = true;
    async function loadServices() {
      try {
        const response = await fetch("/api/services");
        if (!response.ok) throw new Error();
        const data: Service[] = await response.json();
        if (isCurrent)
          setServices(
            data.filter((service) => service.status.toLowerCase() === "active"),
          );
      } catch {
        if (isCurrent) setServicesError("Unable to load services.");
      } finally {
        if (isCurrent) setServicesLoading(false);
      }
    }
    void loadServices();
    return () => {
      isCurrent = false;
    };
  }, []);

  useEffect(() => {
    let isCurrent = true;
    async function loadProviders() {
      try {
        const response = await fetch("/api/providers");
        if (!response.ok) throw new Error();
        const data: Provider[] = await response.json();
        if (isCurrent) setProviders(data);
      } catch {
        if (isCurrent) setProvidersError("Unable to load providers.");
      } finally {
        if (isCurrent) setProvidersLoading(false);
      }
    }
    void loadProviders();
    return () => {
      isCurrent = false;
    };
  }, []);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAvailabilityError("");
    setAvailabilityResult(null);
    if (!serviceId || !date) {
      setAvailabilityError(
        "Select a service and date to find available slots.",
      );
      return;
    }

    const query = new URLSearchParams({
      service_id: serviceId,
      start_date: date,
      end_date: date,
    });
    if (providerId) query.set("provider_id", providerId);
    setAvailabilityLoading(true);
    try {
      const response = await fetch(
        `/api/availability/slots?${query.toString()}`,
      );
      if (!response.ok) throw new Error();
      const data: AvailabilityResponse = await response.json();
      setAvailabilityResult(data);
    } catch {
      setAvailabilityError("Unable to find available slots.");
    } finally {
      setAvailabilityLoading(false);
    }
  }

  return (
    <div className="home-page">
      <section className="home-hero">
        <div className="hero-copy">
          <p className="eyebrow">Appointments made simple</p>
          <h1>
            Book the right appointment, <em>at the right time.</em>
          </h1>
          <p className="hero-intro">
            Find the service you need, choose a provider, and book an available
            time slot in just a few clicks.
          </p>
          <div className="hero-actions">
            <Link className="primary-button" to="/services">
              Book an Appointment <span aria-hidden="true">↗</span>
            </Link>
            <Link className="secondary-button" to="/services">
              Explore Services <span aria-hidden="true">→</span>
            </Link>
          </div>
          <div className="hero-note">
            <span className="status-dot" /> Availability is checked when you
            book
          </div>
        </div>
        <div
          className="hero-visual"
          aria-label="A calm illustration of an appointment calendar"
          role="img"
        >
          <div className="hero-orbit hero-orbit--one" />
          <div className="hero-orbit hero-orbit--two" />
          <div className="calendar-art">
            <div className="calendar-art__top">
              <span>YOUR WEEK</span>
              <strong>October 2026</strong>
              <i>•••</i>
            </div>
            <div className="calendar-art__days">
              <span>M</span>
              <span>T</span>
              <span>W</span>
              <span>T</span>
              <span>F</span>
            </div>
            <div className="calendar-art__dates">
              <span>12</span>
              <span>13</span>
              <b>14</b>
              <span>15</span>
              <span>16</span>
            </div>
            <div className="calendar-art__appointment">
              <span className="appointment-icon">✓</span>
              <div>
                <strong>Consultation</strong>
                <small>10:30 AM · 30 min</small>
              </div>
              <span className="appointment-arrow">↗</span>
            </div>
            <div className="calendar-art__line" />
            <div className="calendar-art__line calendar-art__line--short" />
          </div>
          <span className="hero-sticker hero-sticker--top">
            Good timing <b>✦</b>
          </span>
          <span className="hero-sticker hero-sticker--bottom">
            <b>✓</b> Slot reserved
          </span>
        </div>
      </section>

      <section className="booking-search" aria-labelledby="find-appointment">
        <div className="booking-search__heading">
          <span className="section-number">01</span>
          <div>
            <p className="eyebrow">Start here</p>
            <h2 id="find-appointment">Find your appointment</h2>
          </div>
        </div>
        <form className="booking-form" onSubmit={handleSearch}>
          <label className="home-field">
            Service
            <select
              value={serviceId}
              onChange={(event) => setServiceId(event.target.value)}
              disabled={servicesLoading || services.length === 0}
            >
              <option value="">
                {servicesLoading ? "Loading services..." : "Select a service"}
              </option>
              {services.map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </label>
          <label className="home-field">
            Provider
            <select
              value={providerId}
              onChange={(event) => setProviderId(event.target.value)}
              disabled={providersLoading || providers.length === 0}
            >
              <option value="">
                {providersLoading ? "Loading providers..." : "Any provider"}
              </option>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
          </label>
          <label className="home-field">
            Date
            <input
              type="date"
              min={getToday()}
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={availabilityLoading || servicesLoading}
          >
            {availabilityLoading ? (
              "Finding slots..."
            ) : (
              <>
                Find Available Slots <span aria-hidden="true">→</span>
              </>
            )}
          </button>
        </form>
        {servicesError && (
          <p className="home-form-message home-form-message--error">
            {servicesError}
          </p>
        )}
        {providersError && (
          <p className="home-form-message home-form-message--error">
            {providersError}
          </p>
        )}
        {availabilityError && (
          <p
            className="home-form-message home-form-message--error"
            role="alert"
          >
            {availabilityError}
          </p>
        )}
        {availabilityResult &&
          (availabilityResult.total > 0 ? (
            <p className="home-form-message" role="status">
              {availabilityResult.total} slot
              {availabilityResult.total === 1 ? "" : "s"} available.{" "}
              <Link
                to={{
                  pathname: `/book/${serviceId}`,
                  search: `?${new URLSearchParams({
                    ...(providerId ? { providerId } : {}),
                    date,
                  }).toString()}`,
                }}
              >
                Continue to booking <span aria-hidden="true">→</span>
              </Link>
            </p>
          ) : (
            <p className="home-form-message" role="status">
              No available slots for this date. Try another date or provider.
            </p>
          ))}
      </section>

      <section
        className="home-section services-preview"
        aria-labelledby="popular-services"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">What we offer</p>
            <h2 id="popular-services">Popular Services</h2>
            <p>
              Choose a service and find a convenient time with an available
              provider.
            </p>
          </div>
          <Link className="section-link" to="/services">
            View all services <span aria-hidden="true">↗</span>
          </Link>
        </div>
        {servicesLoading && (
          <p className="status-message">Loading services...</p>
        )}
        {servicesError && (
          <div className="status-message status-message--error" role="alert">
            <strong>We could not load the service list.</strong>
            <span>{servicesError}</span>
          </div>
        )}
        {!servicesLoading && !servicesError && services.length === 0 && (
          <p className="status-message">
            No active services are available right now.
          </p>
        )}
        {!servicesLoading && !servicesError && services.length > 0 && (
          <div className="home-service-grid">
            {services.map((service, index) => (
              <article className="home-service-card" key={service.id}>
                <div className={`service-art service-art--${(index % 3) + 1}`}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                </div>
                <div className="home-service-card__body">
                  <span className="service-category">{service.category}</span>
                  <h3>{service.name}</h3>
                  <p>
                    {service.description ||
                      "Details for this service are coming soon."}
                  </p>
                  <div className="home-service-meta">
                    <span>{service.duration_minutes} min</span>
                    <strong>{formatPrice(service.price)}</strong>
                  </div>
                  <Link
                    to={`/book/${service.id}`}
                    className="service-book-link"
                  >
                    Book Now <span aria-hidden="true">↗</span>
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section
        className="home-section how-section"
        aria-labelledby="how-it-works"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">A better way to book</p>
            <h2 id="how-it-works">How it works</h2>
          </div>
        </div>
        <div className="steps-grid">
          <div className="step-card">
            <span className="step-icon">⌕</span>
            <span className="step-number">01</span>
            <h3>Choose a service</h3>
            <p>Browse the services and select what you need.</p>
          </div>
          <div className="step-card">
            <span className="step-icon">◷</span>
            <span className="step-number">02</span>
            <h3>Choose a time</h3>
            <p>Select a provider, date, and available appointment slot.</p>
          </div>
          <div className="step-card">
            <span className="step-icon">✓</span>
            <span className="step-number">03</span>
            <h3>Confirm your booking</h3>
            <p>Enter your details and confirm your appointment.</p>
          </div>
        </div>
      </section>

      <section className="benefits-strip" aria-label="Platform benefits">
        <div>
          <span>✦</span>
          <strong>Real-time availability</strong>
          <p>See slots based on provider availability.</p>
        </div>
        <div>
          <span>↗</span>
          <strong>Easy booking</strong>
          <p>Book in just a few simple steps.</p>
        </div>
        <div>
          <span>◷</span>
          <strong>Flexible scheduling</strong>
          <p>Choose a time that works for you.</p>
        </div>
        <div>
          <span>⌁</span>
          <strong>Booking notifications</strong>
          <p>Get confirmation and reminders.</p>
        </div>
      </section>

      <section
        className="home-section providers-preview"
        aria-labelledby="meet-providers"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">People you can trust</p>
            <h2 id="meet-providers">Meet Our Providers</h2>
            <p>Experienced professionals, ready when you are.</p>
          </div>
          <Link className="section-link" to="/providers">
            View all providers <span aria-hidden="true">↗</span>
          </Link>
        </div>
        {providersLoading && (
          <p className="status-message">Loading providers...</p>
        )}
        {providersError && (
          <div className="status-message status-message--error" role="alert">
            <strong>We could not load the provider list.</strong>
            <span>{providersError}</span>
          </div>
        )}
        {!providersLoading && !providersError && providers.length === 0 && (
          <p className="status-message">
            No providers are available right now.
          </p>
        )}
        {!providersLoading && !providersError && providers.length > 0 && (
          <div className="provider-preview-grid">
            {providers.slice(0, 3).map((provider, index) => (
              <article className="provider-preview-card" key={provider.id}>
                <div
                  className={`provider-avatar provider-avatar--${providerTones[index % providerTones.length]}`}
                >
                  {getInitials(provider.name)}
                </div>
                <div>
                  <h3>{provider.name}</h3>
                  <p>{provider.type === "person" ? "Provider" : "Resource"}</p>
                  <small>
                    {provider.availability_status.replace("_", " ")}
                  </small>
                </div>
                <Link to="/providers" aria-label={`View ${provider.name}`}>
                  ↗
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="home-cta">
        <div>
          <p className="eyebrow">Your time matters</p>
          <h2>Ready to book your appointment?</h2>
          <p>
            Find an available time that works for you and book your appointment
            today.
          </p>
        </div>
        <Link className="primary-button" to="/services">
          Book an Appointment <span aria-hidden="true">↗</span>
        </Link>
      </section>

      <footer className="home-footer">
        <div>
          <Link className="brand brand--footer" to="/">
            <span className="brand-mark" aria-hidden="true">
              <span />
            </span>
            <span>Appointment Booking</span>
          </Link>
          <p>Simple scheduling for the time that matters.</p>
        </div>
        <div className="footer-links">
          <Link to="/services">Services</Link>
          <Link to="/providers">Providers</Link>
          <Link to="/appointments">My Appointments</Link>
        </div>
        <span className="footer-note">© 2026 Appointment Booking</span>
      </footer>
    </div>
  );
}

function HomePage() {
  const { customer } = useAuth();

  return customer ? <CustomerHomePage /> : <PublicHomePage />;
}

export default HomePage;
