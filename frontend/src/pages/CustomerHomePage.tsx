import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import RescheduleFlow from "../components/RescheduleFlow";
import { useAuth } from "../auth/useAuth";
import {
  cancelCustomerAppointment,
  fetchCustomerAppointments,
  type CustomerAppointment,
} from "../lib/customerAppointments";

type NamedRecord = { id: string; name: string };

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function CustomerHomePage() {
  const { customer, token } = useAuth();
  const [currentTime] = useState(() => Date.now());
  const [appointments, setAppointments] = useState<CustomerAppointment[]>([]);
  const [services, setServices] = useState<Record<string, string>>({});
  const [providers, setProviders] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [rescheduling, setRescheduling] = useState<CustomerAppointment | null>(
    null,
  );

  const loadDashboard = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError("");
    try {
      const [customerAppointments, servicesResponse, providersResponse] =
        await Promise.all([
          fetchCustomerAppointments(token),
          fetch("/api/services"),
          fetch("/api/providers"),
        ]);
      setAppointments(customerAppointments.appointments);
      if (servicesResponse.ok) {
        const data: NamedRecord[] = await servicesResponse.json();
        setServices(
          Object.fromEntries(data.map((item) => [item.id, item.name])),
        );
      }
      if (providersResponse.ok) {
        const data: NamedRecord[] = await providersResponse.json();
        setProviders(
          Object.fromEntries(data.map((item) => [item.id, item.name])),
        );
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load your appointments.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadDashboard(), 0);
    return () => window.clearTimeout(timer);
  }, [loadDashboard]);

  const upcoming = useMemo(
    () =>
      appointments.find(
        (appointment) =>
          ["pending", "confirmed"].includes(appointment.status) &&
          new Date(appointment.appointment_end).getTime() >= currentTime,
      ),
    [appointments, currentTime],
  );
  const recent = appointments
    .filter((appointment) => appointment.id !== upcoming?.id)
    .slice(0, 3);

  async function cancelAppointment(id: string) {
    if (!token || !window.confirm("Cancel this appointment?")) return;

    setActiveAction(id);
    setActionError("");

    try {
      await cancelCustomerAppointment(token, id);

      setAppointments((current) =>
        current.map((appointment) =>
          appointment.id === id
            ? { ...appointment, status: "cancelled" }
            : appointment,
        ),
      );
    } catch (requestError) {
      setActionError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to cancel this appointment.",
      );
    } finally {
      setActiveAction(null);
    }
  }

  const serviceName = (appointment: CustomerAppointment) =>
    services[appointment.service_id] || "Booked service";
  const providerName = (appointment: CustomerAppointment) =>
    providers[appointment.provider_id] || "Your provider";

  return (
    <section className="home-page">
      <section className="home-hero">
        <div className="hero-copy">
          <p className="eyebrow">Your appointments</p>
          <h1>Welcome back, {customer?.name.split(" ")[0]}</h1>
          <p className="hero-intro">
            Keep track of your upcoming appointments and book your next visit
            when you're ready.
          </p>
          <div className="hero-actions">
            <Link className="primary-button" to="/services">
              Book an Appointment <span aria-hidden="true">↗</span>
            </Link>
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

      {error && (
        <div className="status-message status-message--error" role="alert">
          {error}
        </div>
      )}
      {actionError && (
        <div className="status-message status-message--error" role="alert">
          {actionError}
        </div>
      )}
      {isLoading ? (
        <p className="status-message">Loading your schedule...</p>
      ) : (
        <>
          <section
            className="dashboard-panel dashboard-upcoming"
            aria-labelledby="upcoming-appointment"
          >
            <div className="dashboard-section-heading">
              <div>
                <p className="panel-kicker">Next on your calendar</p>
                <h2 id="upcoming-appointment">Upcoming appointment</h2>
              </div>
              <Link className="section-link" to="/appointments">
                View all <span aria-hidden="true">↗</span>
              </Link>
            </div>
            {upcoming ? (
              <div className="dashboard-appointment">
                <div>
                  <span className="appointment-status">{upcoming.status}</span>
                  <h3>{serviceName(upcoming)}</h3>
                  <p>with {providerName(upcoming)}</p>
                </div>
                <dl>
                  <div>
                    <dt>Date</dt>
                    <dd>{formatDate(upcoming.appointment_start)}</dd>
                  </div>
                  <div>
                    <dt>Time</dt>
                    <dd>{formatTime(upcoming.appointment_start)}</dd>
                  </div>
                </dl>
                <div className="appointment-actions">
                  <Link className="secondary-button" to="/appointments">
                    View
                  </Link>
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={activeAction === upcoming.id}
                    onClick={() => setRescheduling(upcoming)}
                  >
                    Reschedule
                  </button>
                  <button
                    className="text-button"
                    type="button"
                    disabled={activeAction === upcoming.id}
                    onClick={() => void cancelAppointment(upcoming.id)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="dashboard-empty">
                <h3>No upcoming appointments</h3>
                <p>Choose a service and reserve a time that works for you.</p>
                <Link className="primary-button" to="/services">
                  Book an Appointment
                </Link>
              </div>
            )}
            {rescheduling && (
              <RescheduleFlow
                appointment={rescheduling}
                serviceName={serviceName(rescheduling)}
                providerName={providerName(rescheduling)}
                token={token!}
                onCancel={() => setRescheduling(null)}
                onComplete={async () => {
                  setRescheduling(null);
                  await loadDashboard();
                }}
              />
            )}
          </section>
          <section
            className="dashboard-panel dashboard-recent"
            aria-labelledby="recent-appointments"
          >
            <div className="dashboard-section-heading">
              <div>
                <p className="panel-kicker">A quick look back</p>
                <h2 id="recent-appointments">Recent appointments</h2>
              </div>
              <Link className="section-link" to="/appointments">
                View all <span aria-hidden="true">↗</span>
              </Link>
            </div>
            {recent.length > 0 ? (
              <div className="recent-appointment-list">
                {recent.map((appointment) => (
                  <div className="recent-appointment" key={appointment.id}>
                    <div>
                      <strong>{serviceName(appointment)}</strong>
                      <span>{formatDate(appointment.appointment_start)}</span>
                    </div>
                    <span
                      className={`appointment-status appointment-status--${appointment.status}`}
                    >
                      {appointment.status}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="dashboard-note">
                Your appointment history will appear here after you book.
              </p>
            )}
          </section>
        </>
      )}
    </section>
  );
}

export default CustomerHomePage;
