import { describe, expect, it } from "vitest";

import type { NetworkEdge, NetworkNode } from "../api/network";
import { buildGraphElements } from "./NetworkTopologyGraph";

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

function networkNode(id: string, label: string): NetworkNode {
  return {
    id,
    label,
    node_type: "physical",
    status: "up",
    details: {},
    warnings: [],
    management: false,
    default_route: false,
  };
}
