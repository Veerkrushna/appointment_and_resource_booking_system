import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { AuthContext } from "./context";

import type { AuthResponse, Customer } from "./context";
const TOKEN_KEY = "customer-access-token";
const CUSTOMER_KEY = "customer-profile";

async function requestAuth(path: string, payload: object) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : "Authentication failed.",
    );
  }
  return (await response.json()) as AuthResponse;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY));
  const [customer, setCustomer] = useState<Customer | null>(() => {
    const saved = sessionStorage.getItem(CUSTOMER_KEY);
    return saved ? (JSON.parse(saved) as Customer) : null;
  });
  const [isLoading, setIsLoading] = useState(Boolean(token));

  useEffect(() => {
    if (!token) return;
    fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } })
      .then((response) =>
        response.ok ? response.json() : Promise.reject(new Error("expired")),
      )
      .then((profile: Customer) => {
        setCustomer(profile);
        sessionStorage.setItem(CUSTOMER_KEY, JSON.stringify(profile));
      })
      .catch(() => {
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(CUSTOMER_KEY);
        setToken(null);
        setCustomer(null);
      })
      .finally(() => setIsLoading(false));
  }, [token]);

  async function authenticate(responsePromise: Promise<AuthResponse>) {
    const response = await responsePromise;
    sessionStorage.setItem(TOKEN_KEY, response.access_token);
    sessionStorage.setItem(CUSTOMER_KEY, JSON.stringify(response.user));
    setToken(response.access_token);
    setCustomer(response.user);
  }

  async function login(email: string, password: string) {
    await authenticate(requestAuth("/api/auth/login", { email, password }));
  }
  async function register(
    name: string,
    email: string,
    password: string,
    phone: string,
  ) {
    await authenticate(
      requestAuth("/api/auth/signup", {
        name,
        email,
        password,
        phone: phone || null,
      }),
    );
  }
  function updateCustomer(profile: Customer) {
    setCustomer(profile);
    sessionStorage.setItem(CUSTOMER_KEY, JSON.stringify(profile));
  }
  function logout() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(CUSTOMER_KEY);
    setToken(null);
    setCustomer(null);
  }

  return (
    <AuthContext.Provider
      value={{
        customer,
        token,
        isLoading,
        login,
        register,
        updateCustomer,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
