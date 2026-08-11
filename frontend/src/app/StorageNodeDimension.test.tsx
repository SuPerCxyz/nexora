import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { StorageOverview, StoragePoolSummary, StorageVolumeSummary } from "../api/contracts";
import { StorageCreatePanel } from "./StorageCreatePanel";
import { StorageTables } from "./StorageTables";

function buildStorage(hostIds: string[], pools: StoragePoolSummary[], volumes: StorageVolumeSummary[]): StorageOverview {
  return { hosts: hostIds.map((id) => ({ id, name: `host-${id}` })), pools, volumes };
}

function pool(id: string, hostId: string): StoragePoolSummary {
  return {
    resource_id: `pool-${id}`,
    host_id: hostId,
    host_name: `host-${hostId}`,
    native_id: id,
    name: `pool-${id}`,
    status: "active",
    pool_type: "dir",
    state: "active",
    active: true,
    autostart: false,
    target_path: "/data",
    capacity_bytes: 100,
    available_bytes: 50,
    writable: true,
  };
}

function volume(id: string, hostId: string, poolId: string): StorageVolumeSummary {
  return {
    resource_id: `vol-${id}`,
    host_id: hostId,
    host_name: `host-${hostId}`,
    pool_resource_id: `pool-${poolId}`,
    pool_name: `pool-${poolId}`,
    name: `vol-${id}`,
    status: "ok",
    format: "qcow2",
    capacity_bytes: 100,
    allocation_bytes: 20,
    in_use: false,
    writable: true,
  };
}

const hosts = ["a", "b"];
const pools = [pool("p1", "a"), pool("p2", "a"), pool("p3", "b")];
const volumes = [volume("v1", "a", "p1"), volume("v2", "b", "p3")];

describe("storage node-dimension filtering", () => {
  it("filters pools and volumes to the selected host", () => {
    render(<StorageTables pools={pools.filter((item) => item.host_id === "a")} volumes={volumes.filter((item) => item.host_id === "a")} loading={false} onLifecycle={vi.fn()} onMutation={vi.fn()} />);

    expect(screen.getByText("pool-p1")).toBeInTheDocument();
    expect(screen.getByText("pool-p2")).toBeInTheDocument();
    expect(screen.queryByText("pool-p3")).not.toBeInTheDocument();
    expect(screen.getAllByText("vol-v1").length).toBeGreaterThan(0);
    expect(screen.queryByText("vol-v2")).not.toBeInTheDocument();
  });

  it("labels referenced volumes as in use", () => {
    render(<StorageTables pools={[]} volumes={[{ ...volume("v1", "a", "p1"), in_use: true }, volume("v2", "a", "p1")]} loading={false} onLifecycle={vi.fn()} onMutation={vi.fn()} />);

    expect(screen.getByText("使用中")).toBeInTheDocument();
    expect(screen.getAllByText("未使用").length).toBeGreaterThan(0);
  });

  it("shows only the selected host pools as volume targets when a node is chosen", async () => {
    render(<StorageCreatePanel storage={buildStorage(hosts, pools, volumes)} selectedHostId="a" loading={false} error={null} onPoolPreview={vi.fn()} onVolumePreview={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "存储卷" }));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: /目标 Pool/ }));

    await waitFor(() => {
      expect(screen.getAllByText("host-a / pool-p1").length).toBeGreaterThan(0);
      expect(screen.getAllByText("host-a / pool-p2").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("host-b / pool-p3")).not.toBeInTheDocument();
  });
});
