import { internalRequest } from "./client";

export type ConsoleCredential = {
  session_id: string;
  token: string;
  kind: "serial" | "vnc";
  vm_uuid: string;
};

export function createConsole(
  hostId: string,
  vmId: string,
  kind: "serial" | "vnc",
): Promise<ConsoleCredential> {
  return internalRequest(
    `/internal/hosts/${encodeURIComponent(hostId)}/vms/${encodeURIComponent(vmId)}/console`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind }),
    },
  );
}
