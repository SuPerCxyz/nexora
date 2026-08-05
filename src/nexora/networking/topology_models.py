"""Bounded transport models for host network topology."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TopologyNode:
    id: str
    label: str
    node_type: str
    status: str
    details: dict[str, object]
    warnings: tuple[str, ...] = ()
    management: bool = False
    default_route: bool = False


@dataclass(frozen=True)
class TopologyEdge:
    id: str
    source: str
    target: str
    relation: str
    warnings: tuple[str, ...] = ()
    management: bool = False


@dataclass(frozen=True)
class NetworkTopology:
    host_id: str
    nodes: tuple[TopologyNode, ...]
    edges: tuple[TopologyEdge, ...]

    @property
    def warning_count(self) -> int:
        return sum(bool(node.warnings) for node in self.nodes) + sum(
            bool(edge.warnings) for edge in self.edges
        )
