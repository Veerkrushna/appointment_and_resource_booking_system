import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchRefundReconciliationCandidates,
  reconcileRefundCandidate,
  reconcileRefundCandidateAndRefresh,
  type RefundReconciliationCandidate,
} from "./paymentReconciliation";
import { RefundReconciliationSection } from "../pages/admin/AdminPaymentReconciliationPage";

const candidate: RefundReconciliationCandidate = {
  refund_id: "refund-local-1",
  status: "PROCESSED",
  amount: 1250,
  currency: "INR",
  razorpay_refund_id: "rfnd-provider-1",
  refund_reason: "Appointment cancellation",
  payment_id: "payment-local-1",
  provider_payment_id: "pay-provider-1",
  provider_order_id: "order-provider-1",
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-02T10:00:00Z",
  investigation_reasons: ["missing_provider_refund_id"],
};

function renderSection({
  candidates = null,
  isLoading = false,
  error = null,
  reconcilingRefundIds = new Set<string>(),
  feedback = {},
}: {
  candidates?: RefundReconciliationCandidate[] | null;
  isLoading?: boolean;
  error?: string | null;
  reconcilingRefundIds?: ReadonlySet<string>;
  feedback?: Record<
    string,
    { kind: "success" | "error"; message: string }
  >;
} = {}) {
  return renderToStaticMarkup(
    createElement(RefundReconciliationSection, {
      candidates,
      isLoading,
      error,
      reconcilingRefundIds,
      feedback,
      onRefresh: () => {},
      onReconcile: () => {},
    }),
  );
}

describe("refund reconciliation UI and API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches candidates with the admin token and renders linked refund details", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([candidate]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const results = await fetchRefundReconciliationCandidates("admin-token");
    const markup = renderSection({ candidates: results });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/payment-reconciliation/refunds?limit=100",
      { headers: { Authorization: "Bearer " + "admin-token" } },
    );
    expect(markup).toContain("Refund reconciliation");
    expect(markup).toContain("refund-local-1");
    expect(markup).toContain("Local status: PROCESSED");
    expect(markup).toContain("INR");
    expect(markup).toContain("Appointment cancellation");
    expect(markup).toContain("Razorpay refund ID");
    expect(markup).toContain("rfnd-provider-1");
    expect(markup).toContain("payment-local-1");
    expect(markup).toContain("pay-provider-1");
    expect(markup).toContain("order-provider-1");
    expect(markup).toContain("missing_provider_refund_id");
    expect(markup).toContain("Created ");
    expect(markup).toContain("Updated ");
    expect(markup).toContain("not independent confirmation");
  });

  it("renders the loading state", () => {
    const markup = renderSection({ isLoading: true });

    expect(markup).toContain("role=\"status\"");
    expect(markup).toContain("Loading refund reconciliation candidates");
    expect(markup).toContain("disabled=\"\"");
  });

  it("renders the empty state after a successful empty response", () => {
    const markup = renderSection({ candidates: [] });

    expect(markup).toContain("No refund candidates were found.");
  });

  it("preserves API failure details and renders an error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Service unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(fetchRefundReconciliationCandidates("admin-token")).rejects.toMatchObject({
      name: "RefundReconciliationApiError",
      status: 503,
      message: "Service unavailable",
    });

    const markup = renderSection({
      error: "The refund reconciliation service is unavailable.",
    });
    expect(markup).toContain("role=\"alert\"");
    expect(markup).toContain("The refund reconciliation service is unavailable.");
  });

  it("clearly displays a missing Razorpay refund ID and missing provider payment identifiers", () => {
    const markup = renderSection({
      candidates: [
        {
          ...candidate,
          razorpay_refund_id: null,
          provider_payment_id: null,
          provider_order_id: null,
        },
      ],
    });

    expect(markup).toContain("Missing Razorpay refund ID");
    expect(markup).toContain("Missing provider payment ID");
    expect(markup).toContain("Missing provider order ID");
    expect(markup).toContain("manual investigation is required");
    expect(markup).toContain("disabled=\"\"");
  });

  it("posts a verification request and returns the reconciled status", async () => {
    const result = {
      refund_id: candidate.refund_id,
      previous_status: "PROCESSING",
      status: "PROCESSED",
      outcome: "updated",
    } as const;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(result), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      reconcileRefundCandidate("admin-token", candidate.refund_id),
    ).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/admin/payment-reconciliation/refunds/${candidate.refund_id}/reconcile`,
      {
        method: "POST",
        headers: { Authorization: "Bearer " + "admin-token" },
      },
    );
  });

  it("refreshes the candidate list after successful verification", async () => {
    const operations: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        operations.push(url.includes("/reconcile") ? "reconcile" : "refresh");
        return new Response(
          JSON.stringify(
            url.includes("/reconcile")
              ? {
                  refund_id: candidate.refund_id,
                  previous_status: "PROCESSING",
                  status: "PROCESSED",
                  outcome: "updated",
                }
              : [],
          ),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }),
    );
    const refresh = async () => {
      await fetchRefundReconciliationCandidates("admin-token");
    };

    await reconcileRefundCandidateAndRefresh(
      "admin-token",
      candidate.refund_id,
      refresh,
    );

    expect(operations).toEqual(["reconcile", "refresh"]);
  });

  it("renders per-refund loading, success, and conflict feedback", () => {
    const loading = renderSection({
      candidates: [candidate],
      reconcilingRefundIds: new Set([candidate.refund_id]),
    });
    expect(loading).toContain("Verifying with Razorpay");
    expect(loading).toContain("disabled=\"\"");

    const success = renderSection({
      candidates: [candidate],
      feedback: {
        [candidate.refund_id]: {
          kind: "success",
          message: "Verified with Razorpay. Local status updated to PROCESSED.",
        },
      },
    });
    expect(success).toContain("role=\"status\"");
    expect(success).toContain("Local status updated to PROCESSED");

    const conflict = renderSection({
      candidates: [candidate],
      feedback: {
        [candidate.refund_id]: {
          kind: "error",
          message: "Conflict requiring manual investigation.",
        },
      },
    });
    expect(conflict).toContain("role=\"alert\"");
    expect(conflict).toContain("Conflict requiring manual investigation");
  });

  it("surfaces safe conflict responses from the reconcile action", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "Refund provider state conflicts with a terminal local state" }),
          {
            status: 409,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(
      reconcileRefundCandidate("admin-token", candidate.refund_id),
    ).rejects.toMatchObject({
      name: "RefundReconciliationApiError",
      status: 409,
    });
  });
});
