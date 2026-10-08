export type PaymentOrderRequest = {
  service_id: string;
  provider_id: string;
  appointment_start: string;
  user_name: string;
  user_email: string;
  user_phone: string | null;
  notes: string | null;
};

export type PaymentOrderResponse = {
  payment_id: string;
  key_id: string;
  order_id: string;
  amount: number;
  currency: string;
  hold_expires_at: string;
};

export type PaymentVerificationRequest = {
  payment_id: string;
  order_id: string;
  provider_payment_id: string;
  signature: string;
};

export class PaymentApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "PaymentApiError";
    this.status = status;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function orderErrorMessage(status: number): string {
  if (status === 401 || status === 403) {
    return "Sign in with a customer account to make a paid booking.";
  }
  if (status === 409) {
    return "This time is no longer available or is already being held. Choose another time.";
  }
  if (status === 422) {
    return "Please check the appointment and recipient details, then try again.";
  }
  if (status >= 500) {
    return "We couldn't confirm whether a payment order was created. Don't retry yet; check your appointments.";
  }
  return "Unable to start payment. Please review the booking and try again.";
}

function verificationErrorMessage(status: number): string {
  if (status === 401 || status === 403) {
    return "Your customer session could not be verified. Sign in again before retrying.";
  }
  if (status === 400) {
    return "The payment could not be verified. Check the payment details or try Checkout again.";
  }
  if (status === 404) {
    return "The payment order could not be found. Contact support before trying another payment.";
  }
  if (status === 409) {
    return "The payment was received, but the booking needs attention. Check your appointments or contact support.";
  }
  if (status >= 500) {
    return "Payment was received, but its status could not be confirmed yet. Check your appointments before trying again.";
  }
  return "The payment could not be verified. Please review the result and try again.";
}

async function post(
  path: string,
  token: string,
  body: object,
  operation: "order" | "verification",
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new PaymentApiError(
      operation === "order"
        ? "We couldn't confirm whether a payment order was created. Don't retry yet; check your appointments."
        : "Payment was received, but its status could not be confirmed yet. Check your appointments before trying again.",
      null,
    );
  }

  if (!response.ok) {
    const message =
      operation === "order"
        ? orderErrorMessage(response.status)
        : verificationErrorMessage(response.status);
    throw new PaymentApiError(message, response.status);
  }

  return response;
}

function isPaymentOrderResponse(value: unknown): value is PaymentOrderResponse {
  return (
    isRecord(value) &&
    typeof value.payment_id === "string" &&
    typeof value.key_id === "string" &&
    typeof value.order_id === "string" &&
    typeof value.amount === "number" &&
    typeof value.currency === "string" &&
    typeof value.hold_expires_at === "string"
  );
}

export async function createPaymentOrder(
  token: string,
  requestBody: PaymentOrderRequest,
): Promise<PaymentOrderResponse> {
  const response = await post(
    "/api/payments/order",
    token,
    requestBody,
    "order",
  );
  let result: unknown;
  try {
    result = await response.json();
  } catch {
    throw new PaymentApiError(
      "We couldn't read the payment order response. Don't retry yet; check your appointments.",
      null,
    );
  }
  if (!isPaymentOrderResponse(result)) {
    throw new PaymentApiError(
      "We couldn't read the payment order response. Don't retry yet; check your appointments.",
      null,
    );
  }
  return result;
}

export async function verifyPayment(
  token: string,
  requestBody: PaymentVerificationRequest,
): Promise<void> {
  await post("/api/payments/verify", token, requestBody, "verification");
}
