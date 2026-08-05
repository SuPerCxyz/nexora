import { internalRequest, setCsrfToken } from "./client";

export type AccountData = {
  administrator: {
    username: string;
    session_timeout_minutes: number;
    global_monospace: boolean;
    density: string;
    language: string;
    timezone: string;
  };
  login_history: Array<{
    occurred_at: string;
    username: string;
    remote_address: string;
    succeeded: boolean;
  }>;
};

export type AccountUpdate = AccountData["administrator"] & {
  current_password: string;
  new_password?: string;
  confirmation?: string;
};

export async function loadAccount(): Promise<AccountData> {
  return internalRequest("/internal/account");
}

export async function updateAccount(values: AccountUpdate): Promise<{ redirect: string; csrf_token: string }> {
  const response = await internalRequest<{ redirect: string; csrf_token: string }>("/internal/account", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  setCsrfToken(response.csrf_token);
  return response;
}

export function logout(): Promise<{ redirect: string }> {
  return internalRequest("/internal/logout", { method: "POST" });
}
