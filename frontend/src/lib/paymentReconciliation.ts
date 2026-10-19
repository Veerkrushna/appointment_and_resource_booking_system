export type PaymentReconciliationHold = {
  id: string;
  status: string;
  expires_at: string;
  appointment_start: string;
  appointment_end: string;
  provider_id: string;
  service_id: string;
};

export type PaymentReconciliationEvent = {
  id: string;
  provider_event_id: string;
  event_type: string;
  provider_order_id: string | null;
  provider_payment_id: string | null;
  capture_validation_failure: string | null;
  capture_validation_details: Record<string, unknown> | null;
  local_payment_state_conflict: boolean;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
};

export type PaymentReconciliationCandidate = {
  payment_id: string;
  status: string;
  amount: number;
  currency: string;
  provider_order_id: string | null;
  provider_payment_id: string | null;
  appointment_id: string | null;
  series_id: string | null;
  created_at: string;
  updated_at: string;
  reasons: string[];
  provider_verification_required: true;
  booking_holds: PaymentReconciliationHold[];
  webhook_events: PaymentReconciliationEvent[];
};

export type RefundReconciliationCandidate = {
  refund_id: string;
  status: string;
  amount: number;
  currency: string;
  razorpay_refund_id: string | null;
  refund_reason: string;
  payment_id: string;
  appointment_id: string | null;
  series_id: string | null;
  provider_payment_id: string | null;
  provider_order_id: string | null;
  created_at: string;
  updated_at: string;
  investigation_reasons: string[];
};

export type RefundReconciliationResult = {
  refund_id: string;
  previous_status: string;
  status: string;
  failure_classification?: string | null;
  outcome:
    | "updated"
    | "unchanged"
    | "no_matching_refund"
    | "multiple_matching_refunds"
    | "provider_unavailable"
    | "evidence_conflict";
};

export class PaymentReconciliationApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "PaymentReconciliationApiError";
    this.status = status;
  }
}

export class RefundReconciliationApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "RefundReconciliationApiError";
    this.status = status;
  }
}

export async function fetchPaymentReconciliationCandidates(
  token: string,
  staleCreatedBefore: string,
  limit: number,
): Promise<PaymentReconciliationCandidate[]> {
  const params = new URLSearchParams({
    stale_created_before: staleCreatedBefore,
    limit: String(limit),
  });

  let response: Response;
  try {
    response = await fetch(`/api/admin/payment-reconciliation?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new PaymentReconciliationApiError(
      "Unable to reach the reconciliation service.",
      null,
    );
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        detail = body.detail;
      }
    } catch {
      detail = "";
    }
    throw new PaymentReconciliationApiError(
      detail || `Reconciliation request failed (${response.status}).`,
      response.status,
    );
  }

  try {
    const result: unknown = await response.json();
    if (!Array.isArray(result)) {
      throw new Error("Expected a candidate list.");
    }
    return result as PaymentReconciliationCandidate[];
  } catch (error) {
    throw new PaymentReconciliationApiError(
      error instanceof Error
        ? error.message
        : "Unable to read reconciliation candidates.",
      response.status,
    );
  }
}

export async function fetchRefundReconciliationCandidates(
  token: string,
  limit = 100,
): Promise<RefundReconciliationCandidate[]> {
  const params = new URLSearchParams({ limit: String(limit) });

  let response: Response;
  try {
    response = await fetch(
      `/api/admin/payment-reconciliation/refunds?${params}`,
      {
        headers: { Authorization: "Bearer " + token },
      },
    );
  } catch {
    throw new RefundReconciliationApiError(
      "Unable to reach the refund reconciliation service.",
      null,
    );
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        detail = body.detail;
      }
    } catch {
      detail = "";
    }
    throw new RefundReconciliationApiError(
      detail || `Refund reconciliation request failed (${response.status}).`,
      response.status,
    );
  }

  try {
    const result: unknown = await response.json();
    if (!Array.isArray(result)) {
      throw new Error("Expected a refund candidate list.");
    }
    return result as RefundReconciliationCandidate[];
  } catch (error) {
    throw new RefundReconciliationApiError(
      error instanceof Error
        ? error.message
        : "Unable to read refund reconciliation candidates.",
      response.status,
    );
  }
}

export async function reconcileRefundCandidate(
  token: string,
  refundId: string,
): Promise<RefundReconciliationResult> {
  let response: Response;
  try {
    response = await fetch(
      `/api/admin/payment-reconciliation/refunds/${encodeURIComponent(refundId)}/reconcile`,
      {
        method: "POST",
        headers: { Authorization: "Bearer " + token },
      },
    );
  } catch {
    throw new RefundReconciliationApiError(
      "Unable to reach the refund reconciliation service.",
      null,
    );
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        detail = body.detail;
      }
    } catch {
      detail = "";
    }
    throw new RefundReconciliationApiError(
      detail || `Refund reconciliation request failed (${response.status}).`,
      response.status,
    );
  }

  try {
    const result: unknown = await response.json();
    if (
      typeof result !== "object" ||
      result === null ||
      !("refund_id" in result) ||
      typeof result.refund_id !== "string" ||
      !("previous_status" in result) ||
      typeof result.previous_status !== "string" ||
      !("status" in result) ||
      typeof result.status !== "string" ||
      !("outcome" in result) ||
      ![
        "updated",
        "unchanged",
        "no_matching_refund",
        "multiple_matching_refunds",
        "provider_unavailable",
        "evidence_conflict",
      ].includes(String(result.outcome))
    ) {
      throw new Error("Invalid refund reconciliation response.");
    }
    return result as RefundReconciliationResult;
  } catch (error) {
    throw new RefundReconciliationApiError(
      error instanceof Error
        ? error.message
        : "Unable to read refund reconciliation result.",
      response.status,
    );
  }
}

export async function reconcileRefundCandidateAndRefresh(
  token: string,
  refundId: string,
  refreshCandidates: () => Promise<void>,
): Promise<RefundReconciliationResult> {
  const result = await reconcileRefundCandidate(token, refundId);
  await refreshCandidates();
  return result;
}
