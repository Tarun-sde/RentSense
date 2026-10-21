import { getQueryClient } from "./query-client";
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface UserSession {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
}

export async function login(
  email: string,
  password: string
): Promise<UserSession> {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || err.detail || "Invalid credentials");
  }
  getQueryClient().clear();
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  getQueryClient().clear();
}

export async function getMe(): Promise<UserSession | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
