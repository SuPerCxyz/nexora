"""Validated inputs for VM Snapshot write operations."""

import json
import re
from dataclasses import asdict, dataclass

from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceType

SNAPSHOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class SnapshotCreateInput:
    vm_base: ResourceBaseVersion
    name: str
    description: str

    def validate(self) -> None:
        if self.vm_base.resource_type != ResourceType.VIRTUAL_MACHINE:
            raise ValueError("Snapshot target must be a virtual machine")
        if not SNAPSHOT_NAME.fullmatch(self.name):
            raise ValueError("Snapshot name must be a safe ASCII identifier")
        if len(self.description) > 512 or any(
            ord(value) < 32 and value not in "\t" for value in self.description
        ):
            raise ValueError("Snapshot description is invalid")

    def encode(self) -> str:
        payload = {
            "vm_base": {
                **asdict(self.vm_base),
                "resource_type": self.vm_base.resource_type.value,
            },
            "name": self.name,
            "description": self.description,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str) -> "SnapshotCreateInput":
        try:
            payload = json.loads(value)
            base = payload["vm_base"]
            result = cls(
                ResourceBaseVersion(
                    str(base["resource_id"]),
                    str(base["host_id"]),
                    ResourceType(str(base["resource_type"])),
                    str(base["native_id"]),
                    int(base["generation"]),
                    str(base["persistent_hash"]),
                    str(base["live_hash"]) if base.get("live_hash") else None,
                ),
                str(payload["name"]),
                str(payload["description"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Snapshot task input is invalid") from exc
        result.validate()
        return result


@dataclass(frozen=True)
class SnapshotDeleteInput:
    vm_base: ResourceBaseVersion
    snapshot_base: ResourceBaseVersion
    name: str

    def validate(self) -> None:
        _validate_target(self.vm_base, self.snapshot_base, self.name)

    def encode(self) -> str:
        payload = {
            "vm_base": _base_payload(self.vm_base),
            "snapshot_base": _base_payload(self.snapshot_base),
            "name": self.name,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str) -> "SnapshotDeleteInput":
        try:
            payload = json.loads(value)
            result = cls(
                _decode_base(payload["vm_base"]),
                _decode_base(payload["snapshot_base"]),
                str(payload["name"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Snapshot delete input is invalid") from exc
        result.validate()
        return result


@dataclass(frozen=True)
class SnapshotRevertInput:
    vm_base: ResourceBaseVersion
    snapshot_base: ResourceBaseVersion
    name: str

    def validate(self) -> None:
        _validate_target(self.vm_base, self.snapshot_base, self.name)

    def encode(self) -> str:
        payload = {
            "vm_base": _base_payload(self.vm_base),
            "snapshot_base": _base_payload(self.snapshot_base),
            "name": self.name,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str) -> "SnapshotRevertInput":
        try:
            payload = json.loads(value)
            result = cls(
                _decode_base(payload["vm_base"]),
                _decode_base(payload["snapshot_base"]),
                str(payload["name"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Snapshot revert input is invalid") from exc
        result.validate()
        return result


def _base_payload(base: ResourceBaseVersion) -> dict[str, object]:
    return {**asdict(base), "resource_type": base.resource_type.value}


def _validate_target(
    vm_base: ResourceBaseVersion,
    snapshot_base: ResourceBaseVersion,
    name: str,
) -> None:
    if vm_base.resource_type != ResourceType.VIRTUAL_MACHINE:
        raise ValueError("Snapshot VM target is invalid")
    if snapshot_base.resource_type != ResourceType.SNAPSHOT:
        raise ValueError("Snapshot target is invalid")
    if vm_base.host_id != snapshot_base.host_id:
        raise ValueError("Snapshot and VM must belong to the same host")
    if not SNAPSHOT_NAME.fullmatch(name):
        raise ValueError("Snapshot name must be a safe ASCII identifier")
    expected = json.dumps([vm_base.native_id, name], separators=(",", ":"))
    if snapshot_base.native_id != expected:
        raise ValueError("Snapshot identity does not match its VM and name")


def _decode_base(base: object) -> ResourceBaseVersion:
    if not isinstance(base, dict):
        raise ValueError("Snapshot resource base is invalid")
    return ResourceBaseVersion(
        str(base["resource_id"]),
        str(base["host_id"]),
        ResourceType(str(base["resource_type"])),
        str(base["native_id"]),
        int(base["generation"]),
        str(base["persistent_hash"]),
        str(base["live_hash"]) if base.get("live_hash") else None,
    )
