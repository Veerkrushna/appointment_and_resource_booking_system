export type Provider = {
  id: string;
  name: string;
  type: "person" | "resource";
  email: string;
  phone: string | null;
  timezone: string;
  availability_status: "available" | "on_leave" | "inactive";
  photo: string | null;
  bio: string | null;
  specializations: string[];
  user_id: string | null;
  created_at: string;
};

export type ProviderCreate = {
  name: string;
  type: "person" | "resource";
  email: string;
  phone?: string;
  timezone?: string;
  availability_status?: "available" | "on_leave" | "inactive";
  photo?: string;
  bio?: string;
  specializations?: string[];
  password: string;
};

export type ProviderUpdate = Partial<ProviderCreate>;

export async function fetchProviders(token: string): Promise<Provider[]> {
  const response = await fetch("/api/providers", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Failed to fetch providers");
  }

  return response.json();
}

export async function createProvider(
  token: string,
  data: ProviderCreate,
): Promise<Provider> {
  const response = await fetch("/api/providers", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || "Failed to create provider");
  }

  return response.json();
}

export async function updateProvider(
  token: string,
  providerId: string,
  data: ProviderUpdate,
): Promise<Provider> {
  const response = await fetch(`/api/providers/${providerId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || "Failed to update provider");
  }

  return response.json();
}

export type Service = {
  id: string;
  name: string;
};

export async function fetchServices(): Promise<Service[]> {
  const response = await fetch("/api/services");
  if (!response.ok) {
    throw new Error("Failed to fetch services");
  }
  return response.json();
}

export async function updateProviderServices(
  token: string,
  providerId: string,
  serviceIds: string[]
): Promise<any> {
  const response = await fetch(`/api/providers/${providerId}/services`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ service_ids: serviceIds }),
  });
  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || "Failed to update provider services");
  }
  return response.json();
}
