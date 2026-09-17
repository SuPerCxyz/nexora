import cytoscape from "cytoscape";
import { useEffect, useRef, useState } from "react";

import type { NetworkEdge, NetworkNode } from "../api/network";
import { designTokens } from "./designTokens";
import { managementInfo, nodeTypeColor, nodeTypeInfo, relationInfo, warningInfo } from "./networkLabels";

const typeLevel: Record<string, number> = {
  physical: 0,
  unknown: 0,
  vlan: 1,
  bridge: 2,
  vnet: 3,
  tap: 3,
  veth: 3,
  vm_nic: 4,
  virtual_machine: 5,
};

const X_SPACING = 96;
const Y_SPACING = 100;

export function NetworkTopologyGraph({ nodes, edges }: { nodes: NetworkNode[]; edges: NetworkEdge[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [themeVersion, setThemeVersion] = useState(0);
  useEffect(() => {
    const observer = new MutationObserver(() => setThemeVersion((value) => value + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!container.current) return;
    const computed = getComputedStyle(document.documentElement);
    const edgeColor = computed.getPropertyValue("--neutral-400").trim() || designTokens.neutral400;
    const labelBackground = computed.getPropertyValue("--background-card").trim() || designTokens.white;
    const labelColor = computed.getPropertyValue("--text-primary").trim() || designTokens.textPrimary;
    const graph = cytoscape({
      container: container.current,
      elements: buildGraphElements(nodes, edges),
      style: [
        { selector: "node", style: { "background-color": (element) => nodeTypeColor[String(element.data("type"))] ?? designTokens.neutral, label: "data(label)", color: designTokens.white, "text-valign": "center", "text-halign": "center", "font-size": 11, width: 64, height: 64 } },
        { selector: "node[management = 'yes']", style: { "border-width": 4, "border-color": designTokens.warning } },
        { selector: "edge", style: { width: 2, color: labelColor, "line-color": edgeColor, "target-arrow-color": edgeColor, "target-arrow-shape": "triangle", "curve-style": "bezier", label: "data(relation_label)", "font-size": 9, "text-background-color": labelBackground, "text-background-opacity": 1, "text-background-padding": "3px" } },
      ],
      layout: { name: "preset", padding: 24 },
    });
    const tooltip = attachTooltip(graph, container.current);
    const resize = () => graph.resize();
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); tooltip(); graph.destroy(); };
  }, [nodes, edges, themeVersion]);
  return <div ref={container} className="nx-network-graph" aria-label="网络拓扑图" />;
}

function attachTooltip(graph: cytoscape.Core, container: HTMLDivElement): () => void {
  const tooltip = document.createElement("div");
  tooltip.className = "nx-cy-tooltip";
  tooltip.style.display = "none";
  container.appendChild(tooltip);
  const hide = () => { tooltip.style.display = "none"; };
  const show = (element: cytoscape.SingularElementArgument) => {
    const content = tooltipContent(element);
    if (!content) { hide(); return; }
    tooltip.replaceChildren(content);
    tooltip.style.display = "block";
    const position = (element as cytoscape.SingularElementReturnValue).renderedPosition();
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;
    let x = position.x;
    let y = position.y - height - 10;
    if (x + width > container.clientWidth - 8) x = container.clientWidth - width - 8;
    if (x < 8) x = 8;
    if (y < 8) y = position.y + 20;
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  };
  graph.on("mouseover", "node", (event) => show(event.target));
  graph.on("mouseout", "node", hide);
  graph.on("mouseover", "edge", (event) => show(event.target));
  graph.on("mouseout", "edge", hide);
  return () => tooltip.remove();
}

function tooltipContent(element: cytoscape.SingularElementArgument): HTMLElement | null {
  const title = document.createElement("div");
  title.className = "nx-cy-tooltip-title";
  const body = document.createElement("div");
  body.className = "nx-cy-tooltip-body";
  if (element.isNode()) {
    const label = String(element.data("label") ?? "");
    const type = String(element.data("type") ?? "");
    const nodeType = nodeTypeInfo(type);
    title.textContent = label;
    appendLine(body, "类型", nodeType.label);
    appendDescription(body, nodeType.description);
    if (element.data("passthrough") === "yes") {
      appendDescription(body, "该网卡为 PCI 透传设备，直接分配宿主机物理网卡给虚拟机使用");
    }
    if (element.data("management") === "yes") {
      appendDescription(body, managementInfo.description);
    }
    const warnings = element.data("warnings") as string[] | undefined;
    for (const warning of warnings ?? []) {
      const info = warningInfo(warning);
      appendLine(body, info.label, info.description);
    }
  } else {
    const source = String(element.data("source") ?? "");
    const target = String(element.data("target") ?? "");
    const relation = relationInfo(String(element.data("relation") ?? ""));
    title.textContent = `${source} → ${target}`;
    appendLine(body, "关系", relation.label);
    appendDescription(body, relation.description);
    const warnings = element.data("warnings") as string[] | undefined;
    for (const warning of warnings ?? []) {
      const info = warningInfo(warning);
      appendLine(body, info.label, info.description);
    }
  }
  if (!body.hasChildNodes()) return null;
  const root = document.createElement("div");
  root.append(title, body);
  return root;
}

function appendLine(container: HTMLElement, label: string, value: string) {
  const row = document.createElement("div");
  row.className = "nx-cy-tooltip-line";
  const key = document.createElement("span");
  key.textContent = `${label}：`;
  row.append(key, document.createTextNode(value));
  container.appendChild(row);
}

function appendDescription(container: HTMLElement, description: string) {
  if (!description) return;
  const row = document.createElement("div");
  row.className = "nx-cy-tooltip-desc";
  row.textContent = description;
  container.appendChild(row);
}

export function buildGraphElements(nodes: NetworkNode[], edges: NetworkEdge[]) {
  const positions = computeLayerPositions(nodes);
  return [
    ...nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.label,
        type: node.node_type,
        management: node.management ? "yes" : "no",
        level: typeLevel[node.node_type] ?? 1,
        warnings: node.warnings,
        passthrough: node.details?.passthrough ? "yes" : "no",
      },
      position: positions[node.id],
    })),
    ...edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        relation: edge.relation,
        relation_label: relationInfo(edge.relation).label,
        warnings: edge.warnings,
      },
    })),
  ];
}

export function computeLayerPositions(nodes: NetworkNode[]) {
  const idsByLevel = new Map<number, string[]>();
  let maxLevel = 0;
  for (const node of nodes) {
    const level = typeLevel[node.node_type] ?? 1;
    if (level > maxLevel) maxLevel = level;
    const ids = idsByLevel.get(level) ?? [];
    ids.push(node.id);
    idsByLevel.set(level, ids);
  }
  const positions: Record<string, { x: number; y: number }> = {};
  for (const [level, ids] of idsByLevel) {
    ids.forEach((id, index) => {
      positions[id] = {
        x: (index - (ids.length - 1) / 2) * X_SPACING,
        y: (maxLevel - level) * Y_SPACING,
      };
    });
  }
  return positions;
}
