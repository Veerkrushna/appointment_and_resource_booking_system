import { afterEach, describe, expect, it, vi } from "vitest";
import { verifyPayment } from "./payments";

describe("verifyPayment", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends separate local and Razorpay payment identifiers", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await verifyPayment("customer-token", {
      payment_id: "local-payment-uuid",
      order_id: "order_razorpay",
      provider_payment_id: "pay_razorpay",
      signature: "razorpay-signature",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/payments/verify",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer customer-token",
        },
        body: JSON.stringify({
          payment_id: "local-payment-uuid",
          order_id: "order_razorpay",
          provider_payment_id: "pay_razorpay",
          signature: "razorpay-signature",
        }),
      }),
    );
  });
});
