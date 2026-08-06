"""Build a read-only network topology from authoritative cached resources."""

import json
from dataclasses import replace
from ipaddress import ip_address

from nexora.hosts.models import Host
from nexora.networking.topology_models import NetworkTopology, TopologyEdge, TopologyNode
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType

MAX_TOPOLOGY_RESOURCES = 20_000
MAX_VM_INTERFACES = 256


def build_network_topology(
    host: Host,
    resources: list[ResourceIndex],
) -> NetworkTopology:
    if len(resources) > MAX_TOPOLOGY_RESOURCES:
        raise ValueError("network topology resource limit exceeded")
    interfaces = [
        item
        for item in resources
        if item.resource_type == ResourceType.HOST_INTERFACE
        and item.status != ResourceStatus.MISSING
    ]
    virtual_machines = [
        item
        for item in resources
        if item.resource_type == ResourceType.VIRTUAL_MACHINE
        and item.status != ResourceStatus.MISSING
    ]
    pci_devices = [
        item
        for item in resources
        if item.resource_type == ResourceType.PCI_DEVICE
        and item.status != ResourceStatus.MISSING
    ]
    nodes, details = _interface_nodes(host, interfaces)
    edges = _interface_edges(nodes, details)
    nodes, edges = _virtual_machine_nodes(nodes, edges, details, virtual_machines, pci_devices)
    nodes, edges = _mark_management(nodes, edges)
    return NetworkTopology(host.id, tuple(nodes), tuple(edges))


def _interface_nodes(
    host: Host,
    resources: list[ResourceIndex],
) -> tuple[list[TopologyNode], dict[str, dict[str, object]]]:
    nodes: list[TopologyNode] = []
    details_by_id: dict[str, dict[str, object]] = {}
    for item in resources:
        details = _details(item)
        node_id = _interface_id(item.native_id)
        details_by_id[node_id] = details
        management = _has_address(details, host.address)
        default_route = _has_default_route(details)
        warnings = _interface_warnings(details)
        nodes.append(
            TopologyNode(
                node_id,
                item.display_name,
                _text(details.get("kind"), "unknown"),
                _text(details.get("operstate"), "unknown").lower(),
                details,
                warnings,
                management,
                default_route,
            )
        )
    return nodes, details_by_id


def _interface_edges(
    nodes: list[TopologyNode],
    details: dict[str, dict[str, object]],
) -> list[TopologyEdge]:
    known = {node.id for node in nodes}
    by_label = {node.label: node.id for node in nodes}
    edges: list[TopologyEdge] = []
    for node in nodes:
        item = details[node.id]
        parent = _resolve_reference(item.get("parent_ifindex"), known, by_label)
        if parent is not None:
            edges.append(_edge(parent, node.id, "parent", details))
        master = _resolve_reference(item.get("master_ifindex"), known, by_label)
        if master is not None:
            source, target = (
                (master, node.id) if node.node_type in {"vnet", "tap"} else (node.id, master)
            )
            edges.append(_edge(source, target, "bridge_port", details))
    return _deduplicate_edges(edges)


def _virtual_machine_nodes(
    nodes: list[TopologyNode],
    edges: list[TopologyEdge],
    interface_details: dict[str, dict[str, object]],
    virtual_machines: list[ResourceIndex],
    pci_devices: list[ResourceIndex],
) -> tuple[list[TopologyNode], list[TopologyEdge]]:
    interface_by_name = {node.label: node.id for node in nodes}
    pci_by_address = {
        _text(_details(item).get("address"), _text(item.native_id, "")): item
        for item in pci_devices
    }
    for vm in virtual_machines:
        vm_id = f"vm:{vm.native_id}"
        vm_details = _details(vm)
        vm_state = _text(vm_details.get("state"), "unknown").lower()
        nodes.append(
            TopologyNode(
                vm_id,
                vm.display_name,
                "virtual_machine",
                vm_state,
                {"uuid": vm.native_id},
            )
        )
        interfaces = vm_details.get("interfaces")
        nic_count = 0
        if isinstance(interfaces, list):
            if len(interfaces) > MAX_VM_INTERFACES:
                raise ValueError("VM interface count exceeds topology limit")
            for index, value in enumerate(interfaces):
                if not isinstance(value, dict):
                    continue
                nic_id = f"nic:{vm.native_id}:{index}"
                nic = {str(key): item for key, item in value.items()}
                label = _text(nic.get("mac"), f"NIC {index + 1}")
                nodes.append(TopologyNode(nic_id, label, "vm_nic", vm_state, nic))
                nic_count += 1
                target_name = _text(nic.get("target"), "")
                source_name = _text(nic.get("source"), "")
                host_interface = interface_by_name.get(target_name) or interface_by_name.get(
                    source_name
                )
                if host_interface is not None:
                    edges.append(_edge(host_interface, nic_id, "vm_attachment", interface_details))
                edges.append(TopologyEdge(f"{nic_id}>{vm_id}", nic_id, vm_id, "belongs_to"))
        host_devices = vm_details.get("host_devices")
        if isinstance(host_devices, list):
            for value in host_devices:
                if not isinstance(value, dict) or value.get("type") != "pci":
                    continue
                address = _hostdev_address(value)
                if address is None:
                    continue
                pci = pci_by_address.get(address)
                if pci is None or not _is_pci_network_card(_details(pci)):
                    continue
                nic_id = f"hostdev:{vm.native_id}:{address}"
                label = _pci_label(address, _details(pci))
                nodes.append(
                    TopologyNode(
                        nic_id,
                        label,
                        "vm_nic",
                        vm_state,
                        {"pci_address": address, "passthrough": True},
                    )
                )
                nic_count += 1
                edges.append(TopologyEdge(f"{nic_id}>{vm_id}", nic_id, vm_id, "belongs_to"))
        if nic_count == 0:
            continue
    return nodes, _deduplicate_edges(edges)


def _hostdev_address(value: dict[str, object]) -> str | None:
    address = value.get("address")
    if not isinstance(address, dict):
        return None
    domain = _text(address.get("domain"), "")
    bus = _text(address.get("bus"), "")
    slot = _text(address.get("slot"), "")
    function = _text(address.get("function"), "")
    if not (domain and bus and slot and function):
        return None
    try:
        return (
            f"{int(domain, 16):04x}:{int(bus, 16):02x}:"
            f"{int(slot, 16):02x}.{int(function, 16)}"
        )
    except ValueError:
        return None


def _is_pci_network_card(details: dict[str, object]) -> bool:
    device_class = _text(details.get("class"), "")
    return device_class.startswith("0x02") or _text(details.get("product"), "").lower() in {
        "ethernet controller",
        "network controller",
    } or "network" in _text(details.get("product"), "").lower()


def _pci_label(address: str, details: dict[str, object]) -> str:
    product = _text(details.get("product"), "")
    if product:
        return f"{address} · {product}"
    return address


def _mark_management(
    nodes: list[TopologyNode],
    edges: list[TopologyEdge],
) -> tuple[list[TopologyNode], list[TopologyEdge]]:
    management = {node.id for node in nodes if node.management}
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if edge.source in management and edge.relation in {"parent", "bridge_port"}:
                changed |= _add(management, edge.target)
            if edge.target in management and edge.relation in {"parent", "bridge_port"}:
                changed |= _add(management, edge.source)
    marked_nodes = [replace(node, management=node.id in management) for node in nodes]
    marked_edges = [
        replace(
            edge,
            management=edge.source in management and edge.target in management,
        )
        for edge in edges
    ]
    return marked_nodes, marked_edges


def _edge(
    source: str,
    target: str,
    relation: str,
    details: dict[str, dict[str, object]],
) -> TopologyEdge:
    warnings: list[str] = []
    source_mtu = details.get(source, {}).get("mtu")
    target_mtu = details.get(target, {}).get("mtu")
    if isinstance(source_mtu, int) and isinstance(target_mtu, int) and source_mtu != target_mtu:
        warnings.append("mtu_mismatch")
    return TopologyEdge(
        f"{source}>{target}:{relation}",
        source,
        target,
        relation,
        tuple(warnings),
    )


def _details(resource: ResourceIndex) -> dict[str, object]:
    try:
        value = json.loads(resource.details_json)
    except json.JSONDecodeError as exc:
        raise ValueError("network topology resource details are invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("network topology resource details are invalid")
    return {str(key): item for key, item in value.items()}


def _interface_id(native_id: str) -> str:
    if not native_id.isdecimal() or not 1 <= int(native_id) <= 2**31 - 1:
        raise ValueError("network interface identity is invalid")
    return f"if:{native_id}"


def _resolve_reference(
    value: object,
    known: set[str],
    by_label: dict[str, str],
) -> str | None:
    if isinstance(value, int) and value >= 1:
        candidate = f"if:{value}"
        return candidate if candidate in known else None
    if isinstance(value, str) and value:
        return by_label.get(value)
    return None


def _has_address(details: dict[str, object], management_address: str) -> bool:
    try:
        expected = str(ip_address(management_address))
    except ValueError:
        return False
    addresses = details.get("addresses")
    return isinstance(addresses, list) and any(
        isinstance(item, dict) and item.get("local") == expected for item in addresses
    )


def _has_default_route(details: dict[str, object]) -> bool:
    routes = details.get("routes")
    return isinstance(routes, list) and any(
        isinstance(item, dict) and item.get("dst") in {"default", "0.0.0.0/0", "::/0"}
        for item in routes
    )


def _interface_warnings(details: dict[str, object]) -> tuple[str, ...]:
    warnings: list[str] = []
    state = _text(details.get("operstate"), "").lower()
    flags = details.get("flags")
    kind = _text(details.get("kind"), "")
    if state in {"down", "lowerlayerdown", "notpresent"}:
        warnings.append("link_down")
    if kind == "physical" and isinstance(flags, list) and "LOWER_UP" not in flags:
        warnings.append("no_carrier")
    return tuple(warnings)


def _deduplicate_edges(edges: list[TopologyEdge]) -> list[TopologyEdge]:
    result: list[TopologyEdge] = []
    seen: set[str] = set()
    for edge in edges:
        if edge.id not in seen:
            seen.add(edge.id)
            result.append(edge)
    return result


def _text(value: object, default: str) -> str:
    return value if isinstance(value, str) and len(value) <= 512 else default


def _add(values: set[str], value: str) -> bool:
    previous = len(values)
    values.add(value)
    return len(values) != previous
