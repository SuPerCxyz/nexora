import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";

import type { NetworkEdge, NetworkNode } from "../api/network";
import { designTokens } from "./designTokens";

const typeColors: Record<string, string> = {
  bridge: designTokens.info,
  vlan: designTokens.special,
  physical: designTokens.success,
  vnet: designTokens.warning,
  vm: designTokens.primary,
  tap: designTokens.neutral,
};

export function NetworkTopologyGraph({ nodes, edges }: { nodes: NetworkNode[]; edges: NetworkEdge[] }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const graph = cytoscape({
      container: container.current,
      elements: buildGraphElements(nodes, edges),
      style: [
        { selector: "node", style: { "background-color": (element) => typeColors[String(element.data("type"))] ?? designTokens.textTertiary, label: "data(label)", color: designTokens.white, "text-valign": "center", "text-halign": "center", "font-size": 11, width: 64, height: 64 } },
        { selector: "node[management = 'yes']", style: { "border-width": 4, "border-color": designTokens.warning } },
        { selector: "edge", style: { width: 2, "line-color": designTokens.neutral400, "target-arrow-color": designTokens.neutral400, "target-arrow-shape": "triangle", "curve-style": "bezier", label: "data(relation)", "font-size": 9, "text-background-color": designTokens.white, "text-background-opacity": 1, "text-background-padding": "3px" } },
      ],
      layout: { name: "cose", animate: false, padding: 32 },
    });
    const resize = () => graph.resize();
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); graph.destroy(); };
  }, [nodes, edges]);
  return <div ref={container} className="nx-network-graph" aria-label="网络拓扑图" />;
}

export function buildGraphElements(nodes: NetworkNode[], edges: NetworkEdge[]) {
  return [
    ...nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.label,
        type: node.node_type,
        management: node.management ? "yes" : "no",
      },
    })),
    ...edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        relation: edge.relation,
      },
    })),
  ];
}
