import { createContext } from "react";

type Customer = {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  role: string;
  is_active: boolean;
};
type AuthResponse = { access_token: string; user: Customer };
type AuthContextValue = {
  customer: Customer | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    name: string,
    email: string,
    password: string,
    phone: string,
  ) => Promise<void>;
  updateCustomer: (customer: Customer) => void;
  logout: () => void;
};

export const AuthContext = createContext<AuthContextValue | null>(null);
export type { AuthContextValue, AuthResponse, Customer };
