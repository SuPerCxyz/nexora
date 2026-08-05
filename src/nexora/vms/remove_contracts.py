"""Validated contracts for VM deletion and rename."""

import json
import re
from dataclasses import asdict, dataclass
from uuid import UUID

from nexora.vms.creation_contracts import NAME_PATTERN


@dataclass(frozen=True)
class VmRemoveInput:
    host_id: str
    resource_id: str
    vm_uuid: str
    vm_name: str
    generation: int
    persistent_hash: str
    operation: str = "delete"
    target_name: str | None = None
    remove_disks: bool = False
    remove_nvram: bool = False

    def validate(self) -> None:
        if not self.host_id or not self.resource_id or not self.vm_uuid or not self.vm_name:
            raise ValueError("VM remove identity is incomplete")
        try:
            UUID(self.vm_uuid)
        except ValueError as exc:
            raise ValueError("VM UUID is invalid") from exc
        if self.generation < 1 or len(self.persistent_hash) != 64:
            raise ValueError("VM remove base version is invalid")
        if self.operation not in {"delete", "rename"}:
            raise ValueError("VM remove operation is unsupported")
        if self.operation == "rename":
            if self.target_name is None or NAME_PATTERN.fullmatch(self.target_name) is None:
                raise ValueError("VM rename target name is invalid")
            if self.target_name == self.vm_name:
                raise ValueError("VM rename target name must differ")
        else:
            if self.target_name is not None:
                raise ValueError("VM delete cannot set a target name")

    def encode(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str) -> "VmRemoveInput":
        if len(value) > 4_096:
            raise ValueError("VM remove input is unavailable")
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError("VM remove input must be an object")
            result = cls(**payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("VM remove input is invalid") from exc
        result.validate()
        return result


_MAC_PATTERN = re.compile(r"(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}")
