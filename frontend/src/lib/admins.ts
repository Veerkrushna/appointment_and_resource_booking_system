export type AdminUser = {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  photo?: string | null;
  role: string;
  is_active: boolean;
  created_at?: string | null;
};

export type AdminUserCreate = {
  name: string;
  email: string;
  password: string;
  role: "ADMIN";
  phone?: string | null;
  photo?: string | null;
};

export async function fetchAdminUsers(token: string): Promise<AdminUser[]> {
  const response = await fetch("/api/admin/users?role=ADMIN", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "Failed to fetch admins");
  }

  return response.json();
}

export async function createAdminUser(
  token: string,
  data: AdminUserCreate,
): Promise<AdminUser> {
  const response = await fetch("/api/admin/users", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "Failed to create admin");
  }

  return response.json();
}

export async function updateAdminUserStatus(
  token: string,
  userId: string,
  isActive: boolean,
): Promise<AdminUser> {
  const response = await fetch(`/api/admin/users/${userId}/status?is_active=${isActive}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "Failed to update admin status");
  }

  return response.json();
}
