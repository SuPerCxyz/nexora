"""Bounded parser for iproute2 JSON host network state."""

import json
from hashlib import sha256

from nexora.resources.contracts import ResourceObservation
from nexora.resources.models import ResourceStatus

MAX_INTERFACES = 16_384


def parse_host_interfaces(
    links_content: bytes,
    addresses_content: bytes,
    routes_content: bytes,
    bridge_links_content: bytes | None,
    bridge_vlans_content: bytes | None,
) -> list[ResourceObservation]:
    links = _records(links_content, "links")
    if len(links) > MAX_INTERFACES:
        raise ValueError("interface count exceeds safety limit")
    addresses = _by_ifindex(_records(addresses_content, "addresses"))
    bridge_links = _by_ifindex(_records(bridge_links_content, "bridge links"))
    bridge_vlans = _by_ifindex(_records(bridge_vlans_content, "bridge VLANs"))
    routes = _records(routes_content, "routes")
    routes_by_device: dict[str, list[dict[str, object]]] = {}
    for route in routes:
        device = route.get("dev")
        if isinstance(device, str):
            routes_by_device.setdefault(device, []).append(_route_summary(route))
    observations = [
        _interface(link, addresses, bridge_links, bridge_vlans, routes_by_device) for link in links
    ]
    identities = [item.native_id for item in observations]
    if len(identities) != len(set(identities)):
        raise ValueError("iproute2 returned duplicate interface indexes")
    return observations


def _interface(
    link: dict[str, object],
    addresses: dict[int, dict[str, object]],
    bridge_links: dict[int, dict[str, object]],
    bridge_vlans: dict[int, dict[str, object]],
    routes: dict[str, list[dict[str, object]]],
) -> ResourceObservation:
    ifindex = _positive_int(link.get("ifindex"), "ifindex")
    ifname = _text(link.get("ifname"), "ifname")
    linkinfo = link.get("linkinfo")
    linkinfo_dict = linkinfo if isinstance(linkinfo, dict) else {}
    inferred_kind = _inferred_kind(ifname, link)
    reported_kind = linkinfo_dict.get("info_kind")
    kind = (
        inferred_kind
        if inferred_kind in {"vnet", "tap"}
        else reported_kind
        if isinstance(reported_kind, str)
        else inferred_kind
    )
    info_data = linkinfo_dict.get("info_data")
    info_data_dict = info_data if isinstance(info_data, dict) else {}
    address_record = addresses.get(ifindex, {})
    parent_index = link.get("link_index")
    parent_link = link.get("link") if kind == "vlan" else None
    details: dict[str, object] = {
        "ifindex": ifindex,
        "ifname": ifname,
        "kind": kind,
        "mac": link.get("address"),
        "mtu": link.get("mtu"),
        "operstate": link.get("operstate"),
        "flags": link.get("flags") if isinstance(link.get("flags"), list) else [],
        "master_ifindex": link.get("master"),
        "parent_ifindex": (
            parent_index if isinstance(parent_index, int) else parent_link
        ),
        "vlan_id": info_data_dict.get("id") if kind == "vlan" else None,
        "addresses": _address_summaries(address_record),
        "routes": routes.get(ifname, []),
        "bridge": _selected_bridge(bridge_links.get(ifindex)),
        "bridge_vlans": _selected_vlans(bridge_vlans.get(ifindex)),
    }
    canonical = json.dumps(
        details,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    parent = parent_index if isinstance(parent_index, int) else parent_link
    return ResourceObservation(
        native_id=str(ifindex),
        parent_native_id=str(parent) if parent is not None else None,
        display_name=ifname,
        status=ResourceStatus.READ_ONLY,
        persistent_hash=None,
        live_hash=sha256(canonical).hexdigest(),
        hash_algorithm="sha256-json-v1",
        details=details,
    )


def _records(content: bytes | None, label: str) -> list[dict[str, object]]:
    if content is None:
        return []
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid iproute2 {label} JSON") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"invalid iproute2 {label} shape")
    return value


def _by_ifindex(records: list[dict[str, object]]) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for item in records:
        ifindex = item.get("ifindex")
        if isinstance(ifindex, int) and ifindex > 0:
            result[ifindex] = item
    return result


def _address_summaries(record: dict[str, object]) -> list[dict[str, object]]:
    values = record.get("addr_info")
    if not isinstance(values, list):
        return []
    return [
        {
            "family": item.get("family"),
            "local": item.get("local"),
            "prefixlen": item.get("prefixlen"),
            "scope": item.get("scope"),
        }
        for item in values
        if isinstance(item, dict)
    ]


def _route_summary(route: dict[str, object]) -> dict[str, object]:
    return {
        key: route.get(key)
        for key in ("dst", "gateway", "prefsrc", "metric", "protocol", "table")
        if key in route
    }


def _selected_bridge(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {key: value.get(key) for key in ("state", "priority", "cost", "hairpin")}


def _selected_vlans(value: dict[str, object] | None) -> list[object]:
    if value is None:
        return []
    vlans = value.get("vlans")
    return vlans if isinstance(vlans, list) else []


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"interface {label} is invalid")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise ValueError(f"interface {label} is invalid")
    return value


def _inferred_kind(ifname: str, link: dict[str, object]) -> str:
    if ifname.startswith("vnet"):
        return "vnet"
    if ifname.startswith("tap"):
        return "tap"
    return "physical" if link.get("link_type") == "ether" else "unknown"
