import { describe, expect, it } from "vitest";

import type { NetworkEdge, NetworkNode } from "../api/network";
import { buildGraphElements, computeLayerPositions } from "./NetworkTopologyGraph";

describe("buildGraphElements", () => {
  it("uses stable topology IDs while preserving duplicate display labels", () => {
    const nodes: NetworkNode[] = [
      networkNode("if:2", "eth0"),
      networkNode("if:3", "eth0"),
    ];
    const edges: NetworkEdge[] = [
      {
        id: "if:2>if:3:bridge_port",
        source: "if:2",
        target: "if:3",
        relation: "bridge_port",
        warnings: [],
        management: false,
      },
    ];

    const elements = buildGraphElements(nodes, edges);

    expect(elements.map((element) => element.data.id)).toEqual([
      "if:2",
      "if:3",
      "if:2>if:3:bridge_port",
    ]);
    expect(elements[0].data).toMatchObject({ label: "eth0" });
    expect(elements[1].data).toMatchObject({ label: "eth0" });
    expect(elements[2].data).toMatchObject({ source: "if:2", target: "if:3" });
  });
});

describe("computeLayerPositions", () => {
  it("places physical at the bottom, vlan above it, bridge above vlan, VM on top", () => {
    const nodes: NetworkNode[] = [
      networkNode("if:10", "eno1", "physical"),
      networkNode("if:20", "eno1.100", "vlan"),
      networkNode("if:30", "br_100", "bridge"),
      networkNode("if:40", "vnet0", "vnet"),
      networkNode("nic:1:0", "52:54:00:12:34:56", "vm_nic"),
      networkNode("vm:1", "web-01", "virtual_machine"),
    ];

    const positions = computeLayerPositions(nodes);

    expect(positions["if:10"].y).toBeGreaterThan(positions["if:20"].y);
    expect(positions["if:20"].y).toBeGreaterThan(positions["if:30"].y);
    expect(positions["if:30"].y).toBeGreaterThan(positions["if:40"].y);
    expect(positions["if:40"].y).toBeGreaterThan(positions["nic:1:0"].y);
    expect(positions["nic:1:0"].y).toBeGreaterThan(positions["vm:1"].y);
    expect(positions["vm:1"].x).toBeCloseTo(positions["if:10"].x);
  });
});

function networkNode(id: string, label: string, nodeType = "physical"): NetworkNode {
  return {
    id,
    label,
    node_type: nodeType,
    status: "up",
    details: {},
    warnings: [],
    management: false,
    default_route: false,
  };
}
