"""Bounded mapping from local resource models to frontend contracts."""

import json

from lxml import etree
from sqlalchemy import text

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.hosts.read_service import HostDetail
from nexora.resources.models import ResourceIndex
from nexora.vms.read_service import VmDetail, VmListItem, VmSnapshotView
from nexora.web.internal.contracts import (
    HostDetailResponse,
    HostMetricSummary,
    HostSummary,
    VmDetailResponse,
    VmDiskSummary,
    VmHostDeviceSummary,
    VmInterfaceSummary,
    VmMetricSummary,
    VmSnapshotSummary,
    VmSummary,
)
from nexora.web.internal.host_presenter import host_features, host_hardware, host_network_adapters
from nexora.xml import LibvirtXmlDocument, XmlSafetyError, XmlStructureError


def host_summary(host: Host) -> HostSummary:
    return HostSummary(
        id=host.id,
        name=host.name,
        address=host.address,
        ssh_port=host.ssh_port,
        status=host.status,
        labels=_labels(host.labels_json),
        last_scanned_at=host.last_scanned_at,
    )


def vm_summary(item: VmListItem, database: Database | None = None) -> VmSummary:
    vcpus = item.details.get("current_vcpus")
    memory_kib = item.details.get("memory_kib")
    state = str(item.details.get("state", item.resource.status))
    return VmSummary(
        resource_id=item.resource.id,
        host_id=item.resource.host_id,
        native_id=item.resource.native_id,
        name=item.resource.display_name,
        host_name=item.host_name,
        state=state,
        status=item.resource.status,
        vcpus=vcpus if isinstance(vcpus, int) else None,
        memory_mib=memory_kib // 1024 if isinstance(memory_kib, int) else None,
        last_seen_at=item.resource.last_seen_at,
        needs_restart=(
            _needs_restart(database, item.resource.host_id, item.resource.native_id, state)
            if database is not None
            else False
        ),
    )


_CONFIG_CHANGE_TASK_TYPES = (
    "vm.cpu_change",
    "vm.memory_change",
    "vm.disk_change",
    "vm.network_change",
    "vm.advanced_change",
    "vm.xml_restore",
)


def _needs_restart(
    database: Database,
    host_id: str,
    vm_uuid: str,
    state: str,
) -> bool:
    if state != "running":
        return False
    in_types = ", ".join(f"'{item}'" for item in _CONFIG_CHANGE_TASK_TYPES)
    with database.session() as session:
        config = session.execute(
            text(
                f"SELECT MAX(finished_at) FROM tasks "
                f"WHERE host_id = :host_id AND vm_uuid = :vm_uuid "
                f"AND task_type IN ({in_types}) AND status = 'succeeded'"
            ),
            {
                "host_id": host_id,
                "vm_uuid": vm_uuid,
            },
        ).scalar()
        started = session.execute(
            text(
                "SELECT MAX(finished_at) FROM tasks "
                "WHERE host_id = :host_id AND vm_uuid = :vm_uuid "
                "AND task_type = 'vm.lifecycle' AND status = 'succeeded' "
                "AND input_summary LIKE '%\"action\":\"start\"%'"
            ),
            {"host_id": host_id, "vm_uuid": vm_uuid},
        ).scalar()
    return config is not None and (started is None or config > started)


def host_detail_response(
    detail: HostDetail,
    metrics: list[dict[str, object]],
    database: Database | None = None,
) -> HostDetailResponse:
    return HostDetailResponse(
        host=host_summary(detail.host),
        ssh_username=detail.host.ssh_username,
        libvirt_uri=detail.host.libvirt_uri,
        resource_counts=detail.resource_counts,
        virtual_machines=[
            vm_summary(VmListItem(item, detail.host.name, _details(item.details_json)), database)
            for item in detail.virtual_machines
        ],
        features=host_features(detail.capabilities, detail.pci_devices),
        hardware=host_hardware(detail.capabilities),
        network_adapters=host_network_adapters(detail.network_interfaces),
        latest_metrics=HostMetricSummary.model_validate(metrics[-1]) if metrics else None,
        manage_url=f"/manage/hosts/{detail.host.id}",
    )


def vm_detail_response(
    detail: VmDetail,
    snapshots: list[VmSnapshotView],
    metrics: list[dict[str, object]],
    database: Database | None = None,
) -> VmDetailResponse:
    values = detail.details
    return VmDetailResponse(
        vm=vm_summary(VmListItem(detail.resource, detail.host.name, values), database),
        active=bool(values.get("active", False)),
        persistent=bool(values.get("persistent", False)),
        autostart=bool(values.get("autostart", False)),
        maximum_vcpus=_integer_or_none(values.get("maximum_vcpus")),
        configuration_status=detail.resource.status,
        disks=[_disk_summary(item) for item in _mapping_list(values.get("disks"))],
        interfaces=[_interface_summary(item) for item in _mapping_list(values.get("interfaces"))],
        host_devices=_host_device_summaries(values, detail.host_device_resources),
        snapshots=[_snapshot_summary(item) for item in snapshots],
        metrics=[VmMetricSummary.model_validate(item) for item in metrics],
        xml=_formatted_xml(detail.documents),
        manage_url=f"/manage/hosts/{detail.host.id}/vms/{detail.resource.native_id}",
    )


def _disk_summary(item: dict[str, object]) -> VmDiskSummary:
    return VmDiskSummary(
        type=_text_or_none(item.get("type")),
        device=_text_or_none(item.get("device")),
        source=_text_or_none(item.get("source")),
        target=_text_or_none(item.get("target")),
        bus=_text_or_none(item.get("bus")),
        format=_text_or_none(item.get("format")),
        readonly=bool(item.get("readonly", False)),
        shareable=bool(item.get("shareable", False)),
    )


def _interface_summary(item: dict[str, object]) -> VmInterfaceSummary:
    return VmInterfaceSummary(
        type=_text_or_none(item.get("type")),
        source=_text_or_none(item.get("source")),
        mac=_text_or_none(item.get("mac")),
        target=_text_or_none(item.get("target")),
        model=_text_or_none(item.get("model")),
    )


def _host_device_summaries(
    values: dict[str, object],
    resources: list[ResourceIndex],
) -> list[VmHostDeviceSummary]:
    indexed = {
        (str(resource.resource_type), str(resource.native_id)): _details(resource.details_json)
        for resource in resources
    }
    summaries: list[VmHostDeviceSummary] = []
    for item in _mapping_list(values.get("host_devices")):
        device_type = _text_or_none(item.get("type")) or "unknown"
        raw_address = item.get("address")
        address: dict[str, object] = raw_address if isinstance(raw_address, dict) else {}
        identity = _host_device_identity(device_type, address)
        details = indexed.get((f"{device_type}_device", identity), {})
        summaries.append(
            VmHostDeviceSummary(
                type=device_type,
                address=identity,
                category=_device_category(device_type, details),
                name=_device_name(device_type, details),
                driver=_text_or_none(details.get("driver")),
                iommu_group=_text_or_none(details.get("iommu_group")),
            )
        )
    return summaries


def _host_device_identity(device_type: str, address: dict[str, object]) -> str:
    if device_type == "pci":
        values = [
            _hex_part(address.get(key), width)
            for key, width in (
                ("domain", 4),
                ("bus", 2),
                ("slot", 2),
                ("function", 1),
            )
        ]
        return f"{values[0]}:{values[1]}:{values[2]}.{values[3]}"
    bus = _text_or_none(address.get("bus")) or "?"
    device = _text_or_none(address.get("device")) or "?"
    return f"USB {bus}:{device}"


def _hex_part(value: object, width: int) -> str:
    try:
        return f"{int(str(value), 16):0{width}x}"
    except ValueError:
        return "?" * width


def _device_category(device_type: str, details: dict[str, object]) -> str:
    if device_type != "pci":
        return "USB 设备"
    class_code = (_text_or_none(details.get("class")) or "").lower()
    categories = {"01": "存储控制器", "02": "网卡", "03": "显卡", "04": "多媒体设备"}
    return categories.get(class_code.removeprefix("0x")[:2], "PCI 设备")


def _device_name(device_type: str, details: dict[str, object]) -> str:
    values = [_text_or_none(details.get(key)) for key in ("vendor", "product")]
    return " · ".join(value for value in values if value) or device_type.upper()


def _snapshot_summary(item: VmSnapshotView) -> VmSnapshotSummary:
    details = item.details
    disks = [str(disk.get("name", "?")) for disk in _mapping_list(details.get("disks"))]
    return VmSnapshotSummary(
        resource_id=item.resource.id,
        name=item.resource.display_name,
        status=item.resource.status,
        state=str(details.get("state", "unknown")),
        creation_time=_text_or_none(details.get("creation_time")),
        current=bool(details.get("current", False)),
        memory=_text_or_none(details.get("memory")),
        disks=disks,
        xml=_format_xml(item.snapshot_xml),
    )


def _formatted_xml(documents: dict[str, str]) -> str:
    return _format_xml(documents.get("persistent_xml") or documents.get("live_xml")) or ""


def _format_xml(content: str | None) -> str | None:
    if not content:
        return None
    try:
        document = LibvirtXmlDocument.parse(content.encode())
        return etree.tostring(document.tree, pretty_print=True, encoding="unicode")
    except (XmlSafetyError, XmlStructureError):
        return None


def _labels(content: str) -> list[str]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return []
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _details(content: str) -> dict[str, object]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _integer_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
