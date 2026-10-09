export {};

declare global {
  interface RazorpayCheckoutSuccess {
    razorpay_payment_id: string;
    razorpay_order_id: string;
    razorpay_signature: string;
  }

  interface RazorpayCheckoutFailure {
    error?: {
      code?: string;
      description?: string;
    };
  }

  interface RazorpayCheckoutOptions {
    key: string;
    amount: number;
    currency: string;
    order_id: string;
    name: string;
    description: string;
    prefill: {
      name: string;
      email: string;
      contact?: string;
    };
    modal: {
      ondismiss: () => void;
    };
    handler: (response: RazorpayCheckoutSuccess) => void;
  }

  interface RazorpayCheckoutInstance {
    open(): void;
    on(
      event: "payment.failed",
      handler: (response: RazorpayCheckoutFailure) => void,
    ): void;
  }

  interface Window {
    Razorpay?: new (
      options: RazorpayCheckoutOptions,
    ) => RazorpayCheckoutInstance;
  }
}
