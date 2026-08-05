"""Validated structured inputs for libvirt storage pool creation."""

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from nexora.remote.validation import validate_host

POOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
NUMERIC_OPTIONS = frozenset({"timeo", "retrans", "rsize", "wsize"})
FLAG_OPTIONS = frozenset({"ro", "rw", "soft", "hard"})
FORBIDDEN_TARGET_ROOTS = frozenset({"/", "/boot", "/dev", "/etc", "/proc", "/run", "/sys", "/usr"})


@dataclass(frozen=True)
class StoragePoolCreateInput:
    host_id: str
    name: str
    pool_type: str
    target_path: str
    source_host: str | None = None
    source_path: str | None = None
    nfs_version: str | None = None
    mount_options: tuple[str, ...] = ()
    start: bool = True
    autostart: bool = True

    def validate(self) -> None:
        if not self.host_id or not POOL_NAME.fullmatch(self.name):
            raise ValueError("invalid storage pool identity")
        _validate_path(self.target_path, target=True)
        if self.pool_type == "dir":
            if any((self.source_host, self.source_path, self.nfs_version, self.mount_options)):
                raise ValueError("dir pool cannot define NFS source fields")
            return
        if self.pool_type != "netfs":
            raise ValueError("only dir and netfs pools are writable")
        if not self.source_host or not self.source_path or self.nfs_version not in {"3", "4"}:
            raise ValueError("netfs pool requires server, export, and NFS version")
        validate_host(self.source_host)
        _validate_path(self.source_path, target=False)
        _validate_mount_options(self.mount_options)

    def encode(self) -> str:
        return json.dumps(
            {
                **vars(self),
                "mount_options": list(self.mount_options),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def decode(cls, value: str) -> "StoragePoolCreateInput":
        if len(value) > 16_384:
            raise ValueError("storage pool input exceeds size limit")
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError("storage pool input must be an object")
            start = payload["start"]
            autostart = payload["autostart"]
            if not isinstance(start, bool) or not isinstance(autostart, bool):
                raise ValueError("storage pool flags must be booleans")
            result = cls(
                host_id=str(payload["host_id"]),
                name=str(payload["name"]),
                pool_type=str(payload["pool_type"]),
                target_path=str(payload["target_path"]),
                source_host=_optional_string(payload.get("source_host")),
                source_path=_optional_string(payload.get("source_path")),
                nfs_version=_optional_string(payload.get("nfs_version")),
                mount_options=tuple(str(item) for item in payload.get("mount_options", [])),
                start=start,
                autostart=autostart,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("storage pool input is invalid") from exc
        result.validate()
        return result


def parse_mount_options(value: str) -> tuple[str, ...]:
    options = tuple(item.strip() for item in value.split(",") if item.strip())
    _validate_mount_options(options)
    return options


def _validate_mount_options(options: tuple[str, ...]) -> None:
    if len(options) > 16 or len(set(options)) != len(options):
        raise ValueError("invalid or duplicate NFS mount option")
    seen_keys: set[str] = set()
    for option in options:
        key, separator, raw_value = option.partition("=")
        if key in seen_keys:
            raise ValueError("duplicate NFS mount option key")
        seen_keys.add(key)
        if not separator and key in FLAG_OPTIONS:
            continue
        if (
            separator
            and key in NUMERIC_OPTIONS
            and raw_value.isascii()
            and raw_value.isdigit()
            and 1 <= int(raw_value) <= 1_073_741_824
        ):
            continue
        raise ValueError("unsupported NFS mount option")
    if {"ro", "rw"} <= seen_keys or {"soft", "hard"} <= seen_keys:
        raise ValueError("conflicting NFS mount options")


def _validate_path(value: str, *, target: bool) -> None:
    if not value or len(value) > 1_024 or "\0" in value:
        raise ValueError("invalid storage path")
    path = PurePosixPath(value)
    if not path.is_absolute() or str(path) != value or "." in path.parts or ".." in path.parts:
        raise ValueError("storage path must be normalized and absolute")
    if target and any(
        value == root or value.startswith(root + "/") for root in FORBIDDEN_TARGET_ROOTS
    ):
        raise ValueError("storage target path is a protected system path")


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional storage field is invalid")
    return value
