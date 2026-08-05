import { internalRequest } from "./client";
import type { MediaItemSummary, TaskCreated } from "./contracts";

export function loadMedia(): Promise<{ items: MediaItemSummary[]; active_task_id: string | null }> {
  return internalRequest("/internal/media");
}

export function scanMedia(): Promise<TaskCreated> {
  return internalRequest("/internal/media/scan", { method: "POST" });
}

export type IssuedMediaCredential = {
  credential_id: string;
  content_url: string;
  token: string;
  expires_at: string;
};

export type MediaCopyOptions = {
  item: { id: string; file_name: string; sha256: string };
  targets: Array<{
    pool_resource_id: string;
    host_name: string;
    pool_name: string;
    target_path: string;
  }>;
};

export function issueMediaCredential(mediaId: string): Promise<IssuedMediaCredential> {
  return internalRequest(`/internal/media/${encodeURIComponent(mediaId)}/credentials`, {
    method: "POST",
  });
}

export function revokeMediaCredential(credentialId: string): Promise<{ revoked: boolean }> {
  return internalRequest(`/internal/media/credentials/${encodeURIComponent(credentialId)}/revoke`, {
    method: "POST",
  });
}

export function loadMediaCopy(mediaId: string): Promise<MediaCopyOptions> {
  return internalRequest(`/internal/media/${encodeURIComponent(mediaId)}/copy`);
}

export function copyMedia(
  mediaId: string,
  values: { pool_resource_id: string; target_file_name: string },
): Promise<TaskCreated> {
  return internalRequest(`/internal/media/${encodeURIComponent(mediaId)}/copy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}
