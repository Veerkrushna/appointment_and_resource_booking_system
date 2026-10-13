import { useState, type FormEvent } from "react";
import { useAuth } from "../../auth/useAuth";
import {
  fetchPaymentReconciliationCandidates,
  PaymentReconciliationApiError,
  type PaymentReconciliationCandidate,
} from "../../lib/paymentReconciliation";

const MAX_RESULT_LIMIT = 500;

function formatTimestamp(timestamp: string) {
  return new Date(timestamp).toLocaleString();
}

function formatAmount(amountInPaise: number, currency: string) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
  }).format(amountInPaise / 100);
}

function requestErrorMessage(error: unknown): string {
  if (!(error instanceof PaymentReconciliationApiError)) {
    return "Unable to load reconciliation candidates.";
  }
  if (error.status === 401) {
    return "Your session could not be verified. Sign in again.";
  }
  if (error.status === 403) {
    return "You do not have permission to view payment reconciliation.";
  }
  if (error.status === 422) {
    return `The cutoff or result limit is invalid. ${error.message}`;
  }
  if (error.status !== null && error.status >= 500) {
    return "The reconciliation service is unavailable. Try again later.";
  }
  return error.message;
}

function CandidateDetails({
  candidate,
}: {
  candidate: PaymentReconciliationCandidate;
}) {
  return (
    <details className="reconciliation-details">
      <summary>
        Holds ({candidate.booking_holds.length}) · Webhook events (
        {candidate.webhook_events.length})
      </summary>
      {candidate.booking_holds.length > 0 && (
        <section>
          <h3>Booking holds</h3>
          <ul>
            {candidate.booking_holds.map((hold) => (
              <li key={hold.id}>
                <strong>{hold.status}</strong>
                <span>
                  Expires {formatTimestamp(hold.expires_at)} · Appointment{" "}
                  {formatTimestamp(hold.appointment_start)} –{" "}
                  {formatTimestamp(hold.appointment_end)}
                </span>
                <small>
                  Hold {hold.id} · Provider {hold.provider_id} · Service{" "}
                  {hold.service_id}
                </small>
              </li>
            ))}
          </ul>
        </section>
      )}
      {candidate.webhook_events.length > 0 && (
        <section>
          <h3>Matching webhook events</h3>
          <ul>
            {candidate.webhook_events.map((event) => (
              <li key={event.id}>
                <strong>
                  {event.status} · {event.event_type}
                </strong>
                <span>
                  Created {formatTimestamp(event.created_at)} · Updated{" "}
                  {formatTimestamp(event.updated_at)}
                  {event.processed_at &&
                    ` · Processed ${formatTimestamp(event.processed_at)}`}
                </span>
                <small>
                  Event {event.provider_event_id}
                  {event.provider_order_id &&
                    ` · Order ${event.provider_order_id}`}
                  {event.provider_payment_id &&
                    ` · Payment ${event.provider_payment_id}`}
                </small>
                {event.error_message && (
                  <p className="reconciliation-event-error">
                    {event.error_message}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {candidate.booking_holds.length === 0 &&
        candidate.webhook_events.length === 0 && (
          <p>No associated holds or matching webhook events were found.</p>
        )}
    </details>
  );
}

export default function AdminPaymentReconciliationPage() {
  const { token } = useAuth();
  const [cutoff, setCutoff] = useState("");
  const [limit, setLimit] = useState(100);
  const [candidates, setCandidates] = useState<
    PaymentReconciliationCandidate[] | null
  >(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadCandidates(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setCandidates(null);
    if (!cutoff) {
      setError("Choose an explicit cutoff date and time.");
      return;
    }
    if (!Number.isInteger(limit) || limit < 1 || limit > MAX_RESULT_LIMIT) {
      setError(`Result limit must be between 1 and ${MAX_RESULT_LIMIT}.`);
      return;
    }
    if (!token) {
      setError("Your session could not be verified. Sign in again.");
      return;
    }

    const cutoffDate = new Date(cutoff);
    if (Number.isNaN(cutoffDate.getTime())) {
      setError("Enter a valid cutoff date and time.");
      return;
    }

    setIsLoading(true);
    try {
      const result = await fetchPaymentReconciliationCandidates(
        token,
        cutoffDate.toISOString(),
        limit,
      );
      setCandidates(result);
    } catch (requestError) {
      setError(requestErrorMessage(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="admin-payment-reconciliation-page">
      <header className="admin-page-header">
        <div>
          <p className="admin-page-eyebrow">Administration</p>
          <h1>Payment reconciliation</h1>
          <p>
            Review local payment records that may need investigation. These
            candidates are not proof of provider capture.
          </p>
        </div>
      </header>

      <aside
        className="reconciliation-safety-notice"
        aria-label="Reconciliation safety notice"
      >
        Independently verify every payment with Razorpay before taking any
        recovery action. This view is read-only and does not retry payments,
        create bookings, convert holds, or issue refunds.
      </aside>

      <form className="reconciliation-controls" onSubmit={loadCandidates}>
        <label>
          Stale payment cutoff
          <input
            type="datetime-local"
            required
            value={cutoff}
            onChange={(event) => setCutoff(event.target.value)}
            aria-describedby="reconciliation-cutoff-help"
          />
          <small id="reconciliation-cutoff-help">
            Applies only to CREATED payments; captured-but-unlinked payments may
            appear regardless of age. Interpreted in{" "}
            {Intl.DateTimeFormat().resolvedOptions().timeZone ||
              "your local timezone"}
            .
          </small>
        </label>
        <label>
          Result limit
          <input
            type="number"
            min={1}
            max={MAX_RESULT_LIMIT}
            required
            value={limit}
            onChange={(event) =>
              setLimit(
                event.target.value === "" ? 0 : Number(event.target.value),
              )
            }
          />
          <small>Between 1 and {MAX_RESULT_LIMIT} candidates.</small>
        </label>
        <button type="submit" disabled={isLoading}>
          {isLoading ? "Loading candidates…" : "Load candidates"}
        </button>
      </form>

      {isLoading && (
        <p className="status-message" role="status">
          Loading payment reconciliation candidates…
        </p>
      )}
      {error && (
        <div className="status-message status-message--error" role="alert">
          {error}
        </div>
      )}
      {!isLoading && !error && candidates?.length === 0 && (
        <p className="reconciliation-empty" role="status">
          No eligible candidates were found for this request.
        </p>
      )}
      {candidates && candidates.length > 0 && (
        <div className="reconciliation-table-wrap">
          <table className="reconciliation-table">
            <thead>
              <tr>
                <th scope="col">Payment ID</th>
                <th scope="col">Amount</th>
                <th scope="col">Status</th>
                <th scope="col">Created</th>
                <th scope="col">Reasons</th>
                <th scope="col">Provider identifiers</th>
                <th scope="col">Related records</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => (
                <tr key={candidate.payment_id}>
                  <td>
                    <code>{candidate.payment_id}</code>
                  </td>
                  <td>{formatAmount(candidate.amount, candidate.currency)}</td>
                  <td>{candidate.status}</td>
                  <td>{formatTimestamp(candidate.created_at)}</td>
                  <td>
                    <ul className="reconciliation-reasons">
                      {candidate.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </td>
                  <td>
                    <span>
                      Order: {candidate.provider_order_id ?? "Missing locally"}
                    </span>
                    <span>
                      Payment:{" "}
                      {candidate.provider_payment_id ?? "Missing locally"}
                    </span>
                  </td>
                  <td>
                    <CandidateDetails candidate={candidate} />
                    {candidate.provider_verification_required && (
                      <strong className="reconciliation-verification-required">
                        Razorpay verification required
                      </strong>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
