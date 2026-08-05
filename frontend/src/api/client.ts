import type { InternalErrorPayload } from "./contracts";

export class InternalApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: InternalErrorPayload,
  ) {
    super(payload.message);
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(value: string): void {
  csrfToken = value;
}

export function getCsrfToken(): string {
  if (!csrfToken) throw new Error("CSRF token is unavailable");
  return csrfToken;
}

export async function internalRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const method = (init.method ?? "GET").toUpperCase();
  if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method)) {
    if (!csrfToken) throw new Error("CSRF token is unavailable");
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers,
  });
  const payload: unknown = await response.json();
  if (!response.ok) throw new InternalApiError(response.status, payload as InternalErrorPayload);
  return payload as T;
}
