import { internalRequest } from "./client";
import type { TaskCreated } from "./contracts";

export type NetworkNode = {
  id: string;
  label: string;
  node_type: string;
  status: string;
  details: Record<string, unknown>;
  warnings: string[];
  management: boolean;
  default_route: boolean;
};

export type NetworkEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
  warnings: string[];
  management: boolean;
};

export type NetworkOverview = {
  hosts: Array<{ id: string; name: string }>;
  selected_host_id: string | null;
  topology: {
    host_id: string;
    warning_count: number;
    nodes: NetworkNode[];
    edges: NetworkEdge[];
  } | null;
};

export type NetworkPreview = {
  plan_id: string;
  confirmation_token: string;
  host_id: string;
  change_type: string;
  target_iface: string;
  rollback_script: string;
};

export function loadNetworks(hostId?: string): Promise<NetworkOverview> {
  const query = hostId ? `?host_id=${encodeURIComponent(hostId)}` : "";
  return internalRequest(`/internal/networks${query}`);
}

export function previewBridge(values: Record<string, unknown>): Promise<NetworkPreview> {
  return post("/internal/networks/bridge/preview", values);
}

export function previewVlan(values: Record<string, unknown>): Promise<NetworkPreview> {
  return post("/internal/networks/vlan/preview", values);
}

export function applyNetwork(preview: NetworkPreview): Promise<TaskCreated> {
  return post("/internal/networks/apply", {
    host_id: preview.host_id,
    plan_id: preview.plan_id,
    confirmation_token: preview.confirmation_token,
  });
}

function post<T>(path: string, body: unknown): Promise<T> {
  return internalRequest<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
