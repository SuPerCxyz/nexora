import { internalRequest, setCsrfToken } from "./client";
import type { InternalSession } from "./contracts";

export async function loadSession(): Promise<InternalSession> {
  const session = await internalRequest<InternalSession>("/internal/session");
  setCsrfToken(session.csrf_token);
  return session;
}
