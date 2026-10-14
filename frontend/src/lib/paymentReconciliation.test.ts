import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchPaymentReconciliationCandidates } from "./paymentReconciliation";

describe("fetchPaymentReconciliationCandidates", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the explicit cutoff, limit, and admin token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchPaymentReconciliationCandidates(
      "admin-token",
      "2026-10-01T12:30:00.000Z",
      25,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/payment-reconciliation?stale_created_before=2026-10-01T12%3A30%3A00.000Z&limit=25",
      { headers: { Authorization: "Bearer admin-token" } },
    );
  });

  it("returns empty and populated candidate responses", async () => {
    const candidate = {
      payment_id: "payment-1",
      status: "CAPTURED",
      amount: 2510,
      currency: "INR",
      provider_order_id: "order-1",
      provider_payment_id: "pay-1",
      appointment_id: null,
      series_id: null,
      created_at: "2026-10-01T10:00:00Z",
      updated_at: "2026-10-01T10:00:00Z",
      reasons: ["captured_unlinked"],
      provider_verification_required: true,
      booking_holds: [],
      webhook_events: [],
    } as const;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([candidate]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchPaymentReconciliationCandidates(
        "admin-token",
        "2026-10-01T12:30:00.000Z",
        25,
      ),
    ).resolves.toEqual([]);
    await expect(
      fetchPaymentReconciliationCandidates(
        "admin-token",
        "2026-10-01T12:30:00.000Z",
        25,
      ),
    ).resolves.toEqual([candidate]);
  });

  it.each([
    [401, "Authentication required"],
    [403, "Insufficient permissions"],
    [422, "stale_created_before must include a timezone"],
    [500, "Server error"],
  ])("preserves HTTP %i errors", async (status, detail) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail }), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(
      fetchPaymentReconciliationCandidates(
        "admin-token",
        "2026-10-01T12:30:00.000Z",
        25,
      ),
    ).rejects.toMatchObject({
      name: "PaymentReconciliationApiError",
      status,
      message: detail,
    });
  });
});
