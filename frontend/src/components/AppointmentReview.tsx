import { useEffect, useRef, useState } from "react";
import {
  createAppointmentReview,
  fetchAppointmentReview,
  updateAppointmentReview,
  type CustomerReview,
  type CustomerReviewInput,
} from "../lib/customerAppointments";

type Props = {
  appointmentId: string;
  providerName: string;
  serviceName: string;
  token: string;
};

type ReviewModalProps = {
  appointmentId: string;
  providerName: string;
  serviceName: string;
  token: string;
  review: CustomerReview | null;
  onClose: () => void;
  onSaved: (review: CustomerReview, wasUpdate: boolean) => void;
};

function ReviewModal({
  appointmentId,
  providerName,
  serviceName,
  token,
  review,
  onClose,
  onSaved,
}: ReviewModalProps) {
  const [rating, setRating] = useState(review?.rating ?? 0);
  const [comment, setComment] = useState(review?.comment ?? "");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSubmitting) onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isSubmitting, onClose]);

  async function submitReview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (rating < 1 || isSubmitting) return;

    const input: CustomerReviewInput = {
      rating,
      comment: comment.trim() || null,
    };
    setError(null);
    setIsSubmitting(true);
    try {
      const savedReview = review
        ? await updateAppointmentReview(token, review.id, input)
        : await createAppointmentReview(token, appointmentId, input);
      onSaved(savedReview, Boolean(review));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to submit your review. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div
      className="appointment-review__backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) onClose();
      }}
    >
      <section
        className="appointment-review__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="appointment-review-title"
      >
        <header className="appointment-review__dialog-header">
          <h2 id="appointment-review-title">
            {review ? "Edit your review" : "Rate your appointment"}
          </h2>
          <button
            ref={closeButtonRef}
            className="appointment-review__close"
            type="button"
            aria-label="Close review dialog"
            disabled={isSubmitting}
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="appointment-review__context">
          <strong>{providerName}</strong>
          <span>{serviceName}</span>
        </div>

        <form onSubmit={(event) => void submitReview(event)}>
          <fieldset className="appointment-review__rating-field">
            <legend>How was your experience?</legend>
            <div
              className="appointment-review__stars"
              role="group"
              aria-label="Rating"
            >
              {[1, 2, 3, 4, 5].map((value) => (
                <button
                  key={value}
                  className={
                    value <= rating
                      ? "appointment-review__star is-selected"
                      : "appointment-review__star"
                  }
                  type="button"
                  aria-label={`${value} ${value === 1 ? "star" : "stars"}`}
                  aria-pressed={rating === value}
                  onClick={() => setRating(value)}
                >
                  {value <= rating ? "★" : "☆"}
                </button>
              ))}
            </div>
          </fieldset>

          <label className="field-label" htmlFor="appointment-review-comment">
            Tell us about your experience (optional)
            <textarea
              id="appointment-review-comment"
              rows={4}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>

          {error && (
            <p className="appointment-review__feedback is-error" role="alert">
              {error}
            </p>
          )}

          <div className="appointment-review__dialog-actions">
            <button
              className="secondary-button"
              type="button"
              disabled={isSubmitting}
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={rating < 1 || isSubmitting}
            >
              {isSubmitting
                ? review
                  ? "Saving..."
                  : "Submitting..."
                : review
                  ? "Save Changes"
                  : "Submit Review"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function AppointmentReview({
  appointmentId,
  providerName,
  serviceName,
  token,
}: Props) {
  const [review, setReview] = useState<CustomerReview | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [loadError, setLoadError] = useState(
    "Unable to load this review. Please try again.",
  );
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let isCurrent = true;

    fetchAppointmentReview(token, appointmentId)
      .then((loadedReview) => {
        if (!isCurrent) return;
        setReview(loadedReview);
        setLoadState("ready");
      })
      .catch((requestError: unknown) => {
        if (!isCurrent) return;
        setLoadError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load this review. Please try again.",
        );
        setLoadState("error");
      });

    return () => {
      isCurrent = false;
    };
  }, [appointmentId, retryCount, token]);

  function handleSaved(savedReview: CustomerReview, wasUpdate: boolean) {
    setReview(savedReview);
    setIsDialogOpen(false);
    setSuccessMessage(
      wasUpdate
        ? "Your review has been updated."
        : "Your review has been submitted.",
    );
  }

  return (
    <div className="appointment-review">
      {loadState === "loading" && (
        <span className="appointment-review__loading" role="status">
          Checking for a review...
        </span>
      )}

      {loadState === "error" && (
        <div className="appointment-review__load-error" role="alert">
          <span>{loadError}</span>
          <button
            className="text-button"
            type="button"
            onClick={() => {
              setLoadState("loading");
              setLoadError("Unable to load this review. Please try again.");
              setRetryCount((count) => count + 1);
            }}
          >
            Try again
          </button>
        </div>
      )}

      {loadState === "ready" && !review && (
        <button
          className="primary-button"
          type="button"
          onClick={() => {
            setSuccessMessage(null);
            setIsDialogOpen(true);
          }}
        >
          Rate Appointment
        </button>
      )}

      {loadState === "ready" && review && (
        <div className="appointment-review__summary">
          <div className="appointment-review__summary-rating">
            <span
              className="appointment-review__summary-stars"
              role="img"
              aria-label={`Your rating: ${review.rating} out of 5 stars`}
            >
              {"★".repeat(review.rating)}
              <span>{"☆".repeat(5 - review.rating)}</span>
            </span>
            <small>Your rating</small>
          </div>
          {review.comment && (
            <blockquote className="appointment-review__comment">
              “{review.comment}”
            </blockquote>
          )}
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              setSuccessMessage(null);
              setIsDialogOpen(true);
            }}
          >
            Edit Review
          </button>
        </div>
      )}

      {successMessage && (
        <p className="appointment-review__feedback" role="status">
          {successMessage}
        </p>
      )}

      {isDialogOpen && (
        <ReviewModal
          appointmentId={appointmentId}
          providerName={providerName}
          serviceName={serviceName}
          token={token}
          review={review}
          onClose={() => setIsDialogOpen(false)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

export default AppointmentReview;
