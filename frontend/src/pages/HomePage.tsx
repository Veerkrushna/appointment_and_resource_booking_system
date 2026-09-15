import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

type Service = {
  id: string;
  name: string;
  description: string;
  duration: string;
  price: string;
  category: string;
};
type Provider = {
  name: string;
  type: string;
  services: string;
  initials: string;
  tone: string;
};

// Replace these records with services and providers API responses when the home feed is connected.
const popularServices: Service[] = [
  {
    id: "general-consultation",
    name: "General Consultation",
    description:
      "A focused conversation to understand your needs and next steps.",
    duration: "30 min",
    price: "₹500",
    category: "Consultation",
  },
  {
    id: "follow-up-consultation",
    name: "Follow-up Consultation",
    description: "Continue your care with a quick check-in and a clear plan.",
    duration: "30 min",
    price: "₹300",
    category: "Consultation",
  },
  {
    id: "specialist-consultation",
    name: "Specialist Consultation",
    description:
      "Dedicated time with an experienced specialist for your concern.",
    duration: "45 min",
    price: "₹700",
    category: "Specialist care",
  },
];

const providers: Provider[] = [
  {
    name: "Dr. Ananya Mehta",
    type: "General physician",
    services: "General & follow-up care",
    initials: "AM",
    tone: "coral",
  },
  {
    name: "Dr. Rohan Kapoor",
    type: "Specialist consultant",
    services: "Specialist consultations",
    initials: "RK",
    tone: "sage",
  },
  {
    name: "Dr. Neha Iyer",
    type: "Family physician",
    services: "General & follow-up care",
    initials: "NI",
    tone: "gold",
  },
];

function HomePage() {
  const navigate = useNavigate();
  const [serviceId, setServiceId] = useState("");

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate(serviceId ? `/book/${serviceId}` : "/services");
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
            >
              <option value="">Select a service</option>
              {popularServices.map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </label>
          <label className="home-field">
            Provider
            <select defaultValue="">
              <option value="">Any provider</option>
              <option value="one">Dr. Ananya Mehta</option>
              <option value="two">Dr. Rohan Kapoor</option>
            </select>
          </label>
          <label className="home-field">
            Date
            <input type="date" min={new Date().toISOString().slice(0, 10)} />
          </label>
          <button className="primary-button" type="submit">
            Find Available Slots <span aria-hidden="true">→</span>
          </button>
        </form>
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
        <div className="home-service-grid">
          {popularServices.map((service, index) => (
            <article className="home-service-card" key={service.id}>
              <div className={`service-art service-art--${index + 1}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
              </div>
              <div className="home-service-card__body">
                <span className="service-category">{service.category}</span>
                <h3>{service.name}</h3>
                <p>{service.description}</p>
                <div className="home-service-meta">
                  <span>{service.duration}</span>
                  <strong>{service.price}</strong>
                </div>
                <Link to={`/book/${service.id}`} className="service-book-link">
                  Book Now <span aria-hidden="true">↗</span>
                </Link>
              </div>
            </article>
          ))}
        </div>
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
        <div className="provider-preview-grid">
          {providers.map((provider) => (
            <article className="provider-preview-card" key={provider.name}>
              <div
                className={`provider-avatar provider-avatar--${provider.tone}`}
              >
                {provider.initials}
              </div>
              <div>
                <h3>{provider.name}</h3>
                <p>{provider.type}</p>
                <small>{provider.services}</small>
              </div>
              <Link to="/providers" aria-label={`View ${provider.name}`}>
                ↗
              </Link>
            </article>
          ))}
        </div>
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

export default HomePage;
