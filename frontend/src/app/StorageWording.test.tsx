import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StorageChangePreviewModal } from "./StorageChangePreviewModal";
import { StorageCreatePanel } from "./StorageCreatePanel";

describe("storage workflow wording", () => {
  it("uses configuration checks instead of plan terminology", () => {
    render(<StorageCreatePanel storage={{ hosts: [], pools: [], volumes: [] }} selectedHostId="__all__" loading={false} error={null} onPoolPreview={vi.fn()} onVolumePreview={vi.fn()} />);

    expect(screen.getByRole("button", { name: "检查创建配置" })).toBeInTheDocument();
    expect(screen.queryByText("预览存储池计划")).not.toBeInTheDocument();
  });

  it("uses direct confirmation wording in the preview", () => {
    render(<StorageChangePreviewModal preview={{ plan_id: "plan-1", confirmation_token: "token", host_id: "host-1", pool_uuid: "pool-1", diff_text: "<pool />", operation: "pool_create", summary: { name: "images" } }} loading={false} error={null} onCancel={vi.fn()} onConfirm={vi.fn()} />);

    expect(screen.getByText("检查存储配置")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认并执行" })).toBeInTheDocument();
  });
});
