import { internalRequest } from "./client";

export type AuditItem = {
  operation_id: string;
  host_id: string;
  host_name: string;
  command_summary: string;
  outcome: string;
  exit_code: number;
  stdout_summary: string;
  stderr_summary: string;
  occurred_at: string;
};

export type AuditPage = {
  items: AuditItem[];
  page: number;
  total: number;
  has_previous: boolean;
  has_next: boolean;
  hosts: Array<{ id: string; name: string }>;
  selected_host_id: string | null;
  selected_outcome: string;
};

export function loadAudit(page = 1, hostId?: string, outcome = "all"): Promise<AuditPage> {
  const query = new URLSearchParams({ page: String(page), outcome });
  if (hostId) query.set("host_id", hostId);
  return internalRequest(`/internal/audit?${query}`);
}
