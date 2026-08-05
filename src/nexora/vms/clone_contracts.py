"""Validated persisted contracts for shutdown full cloning."""

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$")
MAC = re.compile(r"^52:54:00(?::[0-9a-f]{2}){3}$")


@dataclass(frozen=True)
class CloneFile:
    source_path: str
    target_path: str
    partial_path: str
    size_bytes: int
    kind: str


@dataclass(frozen=True)
class VmCloneManifest:
    source_host_id: str
    source_vm_uuid: str
    source_generation: int
    source_hash: str
    target_host_id: str
    target_pool_id: str
    target_pool_uuid: str
    target_pool_generation: int
    target_pool_hash: str
    target_vm_uuid: str
    target_name: str
    mac_addresses: tuple[str, ...]
    files: tuple[CloneFile, ...]
    preserve_identity: bool = False

    def encode(self) -> str:
        payload = {**vars(self), "files": [vars(item) for item in self.files]}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str) -> "VmCloneManifest":
        if len(value) > 131_072:
            raise ValueError("clone manifest is too large")
        payload = json.loads(value)
        values = {
            key: payload[key]
            for key in cls.__dataclass_fields__
            if key not in {"files", "mac_addresses"}
        }
        manifest = cls(
            **values,
            mac_addresses=tuple(payload["mac_addresses"]),
            files=tuple(CloneFile(**item) for item in payload["files"]),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        UUID(self.source_vm_uuid)
        UUID(self.target_vm_uuid)
        UUID(self.target_pool_uuid)
        if (
            self.source_generation < 1
            or self.target_pool_generation < 1
            or len(self.source_hash) != 64
            or len(self.target_pool_hash) != 64
        ):
            raise ValueError("clone resource base version is invalid")
        if not NAME.fullmatch(self.target_name):
            raise ValueError("clone VM name is invalid")
        if self.preserve_identity and self.target_vm_uuid != self.source_vm_uuid:
            raise ValueError("migration target UUID must match the source")
        if not self.files or len(self.files) > 64:
            raise ValueError("clone file count is invalid")
        if any(not MAC.fullmatch(value) for value in self.mac_addresses):
            raise ValueError("clone MAC address is invalid")
        for item in self.files:
            _validate_file(item)


def _validate_file(item: CloneFile) -> None:
    for value in (item.source_path, item.target_path, item.partial_path):
        path = PurePosixPath(value)
        if not path.is_absolute() or ".." in path.parts or "\0" in value:
            raise ValueError("clone file path is invalid")
    if item.kind not in {"disk", "nvram"} or item.size_bytes < 0:
        raise ValueError("clone file metadata is invalid")
