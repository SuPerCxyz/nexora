"""Pure validation and display helpers for VM Snapshot changes."""

import json
from pathlib import PurePosixPath

from nexora.resources.contracts import ResourceObservation
from nexora.resources.models import ResourceIndex, ResourceStatus
from nexora.vms.snapshot_contracts import (
    SnapshotCreateInput,
    SnapshotDeleteInput,
    SnapshotRevertInput,
)
from nexora.vms.snapshot_errors import SnapshotChangeConflict, SnapshotChangeError


def supported_disks(observation: ResourceObservation) -> list[str]:
    disks = observation.details.get("disks")
    if not isinstance(disks, list):
        raise SnapshotChangeConflict("VM disk inventory is unavailable")
    writable: list[str] = []
    for disk in disks:
        if not isinstance(disk, dict) or disk.get("device") != "disk" or disk.get("readonly"):
            continue
        source = disk.get("source")
        target = disk.get("target")
        if (
            disk.get("type") != "file"
            or disk.get("format") != "qcow2"
            or not isinstance(source, str)
            or not PurePosixPath(source).is_absolute()
            or not isinstance(target, str)
            or not target
        ):
            raise SnapshotChangeConflict(
                "internal Snapshot requires every writable disk to be file/qcow2"
            )
        writable.append(target)
    if not writable:
        raise SnapshotChangeConflict("VM has no writable qcow2 disk to snapshot")
    return writable


def verify_created(snapshot: ResourceIndex | None) -> None:
    if snapshot is None or snapshot.status != ResourceStatus.MANAGED:
        raise SnapshotChangeError("created Snapshot was not discovered")
    try:
        details = json.loads(snapshot.details_json)
        disks = details["disks"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SnapshotChangeError("created Snapshot details are invalid") from exc
    if details.get("memory") != "no" or not isinstance(disks, list):
        raise SnapshotChangeError("created Snapshot has an unexpected memory mode")
    modes = [disk.get("snapshot") for disk in disks if isinstance(disk, dict)]
    if "internal" not in modes or any(mode not in {"internal", "no"} for mode in modes):
        raise SnapshotChangeError("created Snapshot has an unsafe disk mode")


def creation_diff(create: SnapshotCreateInput, disks: list[str]) -> str:
    values = [
        "+ operation: create internal disk Snapshot",
        f"+ name: {create.name}",
        f"+ description: {create.description or '(empty)'}",
        "+ memory: no",
        *[f"+ disk: {disk} internal" for disk in disks],
    ]
    return "\n".join(values)


def snapshot_native_id(vm_uuid: str, name: str) -> str:
    return json.dumps([vm_uuid, name], separators=(",", ":"))


def validate_deletable(
    delete: SnapshotDeleteInput | SnapshotRevertInput,
    target: ResourceIndex | None,
    snapshots: list[ResourceIndex],
) -> None:
    if target is None or target.status != ResourceStatus.MANAGED:
        raise SnapshotChangeConflict("Snapshot is unavailable for deletion")
    if (
        target.id != delete.snapshot_base.resource_id
        or target.native_id != delete.snapshot_base.native_id
        or target.persistent_hash != delete.snapshot_base.persistent_hash
    ):
        raise SnapshotChangeConflict("Snapshot changed after the page was opened")
    details = _snapshot_details(target)
    disks = details.get("disks")
    if details.get("memory") != "no" or not isinstance(disks, list):
        raise SnapshotChangeConflict("only disk-only Snapshots can be deleted")
    modes = [disk.get("snapshot") for disk in disks if isinstance(disk, dict)]
    if "internal" not in modes or any(mode not in {"internal", "no"} for mode in modes):
        raise SnapshotChangeConflict("only internal Snapshot disks can be deleted")
    if any(_snapshot_details(item).get("parent_name") == delete.name for item in snapshots):
        raise SnapshotChangeConflict("Snapshot has children and is not a leaf")


def deletion_diff(delete: SnapshotDeleteInput, target: ResourceIndex) -> str:
    details = _snapshot_details(target)
    values = [
        "- operation: delete internal leaf Snapshot",
        f"- name: {delete.name}",
        f"- current: {str(bool(details.get('current'))).lower()}",
        "- memory: no",
        "- children: none",
    ]
    return "\n".join(values)


def validate_revertable(
    revert: SnapshotRevertInput,
    target: ResourceIndex | None,
    snapshots: list[ResourceIndex],
) -> None:
    validate_deletable(revert, target, snapshots)
    assert target is not None
    details = _snapshot_details(target)
    if details.get("current") is not True:
        raise SnapshotChangeConflict("only the current Snapshot can be reverted")
    if details.get("state") != "shutoff":
        raise SnapshotChangeConflict("Snapshot must record a shut-off VM")
    if details.get("domain_hash") != revert.vm_base.persistent_hash:
        raise SnapshotChangeConflict("Snapshot Domain configuration differs from the current VM")


def revert_diff(revert: SnapshotRevertInput, target: ResourceIndex) -> str:
    details = _snapshot_details(target)
    return "\n".join(
        (
            "~ operation: revert disk data to current internal leaf Snapshot",
            f"~ name: {revert.name}",
            f"= domain hash: {details.get('domain_hash')}",
            "= VM state after revert: shutoff",
            "! guest disk writes after Snapshot will be permanently discarded",
        )
    )


def _snapshot_details(snapshot: ResourceIndex) -> dict[str, object]:
    try:
        details = json.loads(snapshot.details_json)
    except json.JSONDecodeError as exc:
        raise SnapshotChangeError("Snapshot details are invalid") from exc
    if not isinstance(details, dict):
        raise SnapshotChangeError("Snapshot details are invalid")
    return details
