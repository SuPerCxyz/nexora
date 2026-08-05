import type {
  HostKeyConfirmation,
  HostOnboardingRequest,
  HostOnboardingStarted,
  TaskCreated,
} from "./contracts";
import { internalRequest } from "./client";

export function beginHostOnboarding(
  submitted: HostOnboardingRequest,
): Promise<HostOnboardingStarted> {
  return internalRequest<HostOnboardingStarted>("/internal/hosts/onboarding", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submitted),
  });
}

export function loadHostKeyConfirmation(hostId: string): Promise<HostKeyConfirmation> {
  return internalRequest<HostKeyConfirmation>(
    `/internal/hosts/${encodeURIComponent(hostId)}/host-key-confirmation`,
  );
}

export function confirmHostKey(
  hostId: string,
  hostKeyDigest: string,
): Promise<TaskCreated> {
  return internalRequest<TaskCreated>(
    `/internal/hosts/${encodeURIComponent(hostId)}/host-key-confirmation`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host_key_digest: hostKeyDigest }),
    },
  );
}
