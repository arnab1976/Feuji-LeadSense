/**
 * Thin API client.
 *
 * One place that knows the base URL and how the bearer token is attached, so
 * swapping the dev token for an MSAL-acquired Entra ID token is a change here
 * and nowhere else.
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";

const TOKEN_KEY = "leadsense.token";
const USER_KEY = "leadsense.user";

export type SessionUser = {
  id: string;
  email: string;
  name: string;
  role: string;
  tenant_id: string;
  tenant_name: string;
  permissions?: string[];
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setSession(token: string, user: SessionUser) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getUser(): SessionUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as SessionUser) : null;
}

export function clearSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && init.body) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const text = await res.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      throw new ApiError(
        `API returned HTML instead of JSON (${res.status}). Confirm the backend is running on port 8000.`,
        res.status,
        text.slice(0, 160)
      );
    }
  }

  if (!res.ok) {
    const body = payload as { message?: string; detail?: unknown } | null;
    const message =
      (body && (body.message || body.detail)) || `Request failed (${res.status})`;
    throw new ApiError(String(message), res.status, body?.detail);
  }
  return payload as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T,>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};

export async function signIn(
  tenantSlug: string,
  role: string,
  email: string,
  name: string
) {
  const res = await request<{ access_token: string; user: SessionUser }>(
    "/auth/dev-token",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_slug: tenantSlug, role, email, name }),
    }
  );
  setSession(res.access_token, res.user);
  return res.user;
}
