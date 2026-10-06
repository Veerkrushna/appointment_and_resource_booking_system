import { useState } from "react";

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => RazorpayInstance;
  }
}

export interface RazorpaySuccessResponse {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

export interface RazorpayOptions {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (response: RazorpaySuccessResponse) => void;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  notes?: Record<string, string>;
  theme?: {
    color?: string;
  };
  modal?: {
    ondismiss?: () => void;
  };
}

export interface RazorpayInstance {
  open: () => void;
  on: (event: string, handler: (response: unknown) => void) => void;
}

export interface PayButtonProps {
  bookingId: string;
  onPaid: () => void;
  customerName?: string;
  customerEmail?: string;
  customerPhone?: string;
  className?: string;
  disabled?: boolean;
  onPaymentFailed?: (errorMessage: string) => void;
}

function loadRazorpaySdk(): Promise<boolean> {
  return new Promise((resolve) => {
    if (typeof window.Razorpay === "function") {
      resolve(true);
      return;
    }

    const scriptId = "razorpay-checkout-sdk";
    const existingScript = document.getElementById(scriptId) as HTMLScriptElement | null;

    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(true));
      existingScript.addEventListener("error", () => resolve(false));
      return;
    }

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

export default function PayButton({
  bookingId,
  onPaid,
  customerName,
  customerEmail,
  customerPhone,
  className = "primary-button",
  disabled = false,
  onPaymentFailed,
}: PayButtonProps) {
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handlePayment() {
    if (loading || disabled || !bookingId) return;

    setLoading(true);
    setErrorMessage(null);

    try {
      // 1. Ensure Razorpay SDK is loaded
      const isSdkLoaded = await loadRazorpaySdk();
      if (!isSdkLoaded || typeof window.Razorpay !== "function") {
        throw new Error(
          "Could not load Razorpay checkout SDK. Please verify your internet connection.",
        );
      }

      // 2. Call POST /payments/create-order
      const orderResponse = await fetch("/payments/create-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ booking_id: bookingId }),
      });

      if (!orderResponse.ok) {
        let errorDetail = "Failed to initiate payment.";
        try {
          const errorJson = await orderResponse.json();
          if (errorJson.detail) {
            errorDetail = errorJson.detail;
          }
        } catch {
          // Fallback to default
        }
        throw new Error(errorDetail);
      }

      const orderData = (await orderResponse.json()) as {
        order_id: string;
        amount: number;
        currency: string;
        key_id: string;
      };

      // 3. Open Razorpay Checkout popup
      const options: RazorpayOptions = {
        key: orderData.key_id,
        amount: orderData.amount,
        currency: orderData.currency,
        name: "Appointment Booking",
        description: "Complete your appointment booking payment",
        order_id: orderData.order_id,
        handler: async (response: RazorpaySuccessResponse) => {
          setLoading(true);
          try {
            const verifyResponse = await fetch("/payments/verify", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
              }),
            });

            if (!verifyResponse.ok) {
              let verifyDetail = "Payment verification failed.";
              try {
                const verifyJson = await verifyResponse.json();
                if (verifyJson.detail) verifyDetail = verifyJson.detail;
              } catch {
                // Fallback
              }
              throw new Error(verifyDetail);
            }

            setLoading(false);
            onPaid();
          } catch (verifyError) {
            setLoading(false);
            const msg =
              verifyError instanceof Error
                ? verifyError.message
                : "Payment verification failed.";
            setErrorMessage(msg);
            onPaymentFailed?.(msg);
          }
        },
        prefill: {
          name: customerName,
          email: customerEmail,
          contact: customerPhone,
        },
        theme: {
          color: "#2563eb",
        },
        modal: {
          ondismiss: () => {
            setLoading(false);
          },
        },
      };

      const razorpayInstance = new window.Razorpay(options);
      razorpayInstance.on("payment.failed", (failedEvent: unknown) => {
        setLoading(false);
        const reason =
          typeof failedEvent === "object" &&
          failedEvent !== null &&
          "error" in failedEvent &&
          typeof (failedEvent as { error?: { description?: string } }).error?.description ===
            "string"
            ? (failedEvent as { error: { description: string } }).error.description
            : "Payment failed or was cancelled.";
        setErrorMessage(reason);
        onPaymentFailed?.(reason);
      });

      razorpayInstance.open();
    } catch (err) {
      setLoading(false);
      const msg =
        err instanceof Error ? err.message : "Unable to initiate payment.";
      setErrorMessage(msg);
      onPaymentFailed?.(msg);
    }
  }

  return (
    <div className="pay-button-container" style={{ display: "inline-block" }}>
      <button
        type="button"
        className={className}
        disabled={disabled || loading}
        onClick={() => void handlePayment()}
      >
        {loading ? "Processing payment..." : "Pay with Razorpay (Test Mode)"}
      </button>
      {errorMessage && (
        <p
          className="status-message status-message--error"
          role="alert"
          style={{ marginTop: "0.5rem" }}
        >
          {errorMessage}
        </p>
      )}
    </div>
  );
}
