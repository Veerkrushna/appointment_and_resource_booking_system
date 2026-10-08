import type { PaymentOrderResponse } from "./payments";

const CHECKOUT_SCRIPT_URL = "https://checkout.razorpay.com/v1/checkout.js";
let checkoutScriptPromise: Promise<void> | null = null;

export type CheckoutResult =
  | { kind: "success"; response: RazorpayCheckoutSuccess }
  | { kind: "dismissed" }
  | { kind: "failed" };

export async function loadRazorpayCheckout(): Promise<void> {
  if (window.Razorpay) return;
  if (checkoutScriptPromise) return checkoutScriptPromise;

  checkoutScriptPromise = new Promise<void>((resolve, reject) => {
    let script = document.querySelector<HTMLScriptElement>(
      `script[src="${CHECKOUT_SCRIPT_URL}"]`,
    );
    const isNewScript = script === null;

    if (!script) {
      script = document.createElement("script");
      script.src = CHECKOUT_SCRIPT_URL;
      script.async = true;
    }

    const onLoad = () => {
      cleanup();
      if (window.Razorpay) {
        resolve();
      } else {
        checkoutScriptPromise = null;
        script?.remove();
        reject(new Error("Razorpay Checkout did not initialize."));
      }
    };
    const onError = () => {
      cleanup();
      checkoutScriptPromise = null;
      if (isNewScript) script?.remove();
      reject(new Error("Unable to load Razorpay Checkout."));
    };
    const cleanup = () => {
      script?.removeEventListener("load", onLoad);
      script?.removeEventListener("error", onError);
    };

    script.addEventListener("load", onLoad, { once: true });
    script.addEventListener("error", onError, { once: true });
    if (isNewScript) document.head.appendChild(script);
  });

  return checkoutScriptPromise;
}

export async function openRazorpayCheckout(
  order: PaymentOrderResponse,
  serviceName: string,
  providerName: string | undefined,
  recipientName: string,
  recipientEmail: string,
  recipientPhone: string | null | undefined,
): Promise<CheckoutResult> {
  await loadRazorpayCheckout();
  const Razorpay = window.Razorpay;
  if (!Razorpay) {
    throw new Error("Razorpay Checkout is unavailable.");
  }

  return new Promise<CheckoutResult>((resolve, reject) => {
    let settled = false;
    const settle = (result: CheckoutResult) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    try {
      const checkout = new Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        order_id: order.order_id,
        name: "Appointment Booking",
        description: providerName
          ? `${serviceName} with ${providerName}`
          : serviceName,
        prefill: {
          name: recipientName,
          email: recipientEmail,
          contact: recipientPhone || undefined,
        },
        modal: {
          ondismiss: () => settle({ kind: "dismissed" }),
        },
        handler: (response) => settle({ kind: "success", response }),
      });
      checkout.on("payment.failed", () => settle({ kind: "failed" }));
      checkout.open();
    } catch {
      reject(new Error("Unable to open Razorpay Checkout."));
    }
  });
}
