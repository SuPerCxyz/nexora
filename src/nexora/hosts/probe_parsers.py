"""Bounded parsers for standard read-only host command output."""

import json

from nexora.hosts.capabilities import JsonValue


def parse_os_release(output: bytes) -> JsonValue:
    values: dict[str, JsonValue] = {}
    for raw_line in output.decode("utf-8", errors="replace").splitlines()[:256]:
        if "=" not in raw_line:
            continue
        name, value = raw_line.split("=", 1)
        if name in {"ID", "VERSION_ID", "PRETTY_NAME", "NAME"}:
            values[name.lower()] = value.strip().strip("\"'")
    return values


def parse_nodeinfo(output: bytes) -> JsonValue:
    values: dict[str, JsonValue] = {}
    integer_fields = {
        "CPU(s)": "cpus",
        "CPU socket(s)": "sockets",
        "Core(s) per socket": "cores_per_socket",
        "Thread(s) per core": "threads_per_core",
        "NUMA cell(s)": "numa_cells",
        "Memory size": "memory_kib",
    }
    for raw_line in output.decode("utf-8", errors="replace").splitlines()[:128]:
        if ":" not in raw_line:
            continue
        name, raw_value = (part.strip() for part in raw_line.split(":", 1))
        if name == "CPU model":
            values["cpu_model"] = raw_value
        elif name in integer_fields:
            number = raw_value.split()[0]
            if number.isdigit():
                values[integer_fields[name]] = int(number)
    return values


def parse_lscpu(output: bytes) -> JsonValue:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError("lscpu output is invalid") from exc
    rows = payload.get("lscpu") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("lscpu output is invalid")
    selected = {
        "Architecture": "architecture",
        "CPU(s)": "logical_cpus",
        "Model name": "model_name",
        "Socket(s)": "sockets",
        "Core(s) per socket": "cores_per_socket",
        "Thread(s) per core": "threads_per_core",
        "NUMA node(s)": "numa_nodes",
        "Vendor ID": "vendor_id",
        "Virtualization": "virtualization",
    }
    integers = {"logical_cpus", "sockets", "cores_per_socket", "threads_per_core", "numa_nodes"}
    values: dict[str, JsonValue] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        field = row.get("field")
        data = row.get("data")
        name = field.rstrip(":") if isinstance(field, str) else None
        key = selected.get(name or "")
        if key is None or not isinstance(data, str) or len(data) > 512:
            continue
        values[key] = int(data) if key in integers and data.isdigit() else data
    return values


def parse_lines(output: bytes, *, limit: int = 10_000) -> JsonValue:
    return [line for line in output.decode("utf-8", errors="replace").splitlines()[:limit] if line]
