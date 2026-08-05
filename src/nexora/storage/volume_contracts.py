"""Validated structured inputs for storage volume changes."""

import json
import re
from dataclasses import dataclass
from uuid import UUID

VOLUME_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
MIN_CAPACITY = 1024 * 1024
MAX_CAPACITY = 8 * 1024**5


@dataclass(frozen=True)
class StorageVolumeCreateInput:
    host_id: str
    pool_resource_id: str
    pool_uuid: str
    pool_generation: int
    pool_hash: str
    name: str
    volume_format: str
    capacity_bytes: int

    def validate(self) -> None:
        if not self.host_id or not self.pool_resource_id:
            raise ValueError("storage volume pool identity is invalid")
        try:
            UUID(self.pool_uuid)
        except ValueError as exc:
            raise ValueError("storage volume pool UUID is invalid") from exc
        if self.pool_generation < 1 or not _valid_hash(self.pool_hash):
            raise ValueError("storage volume pool version is invalid")
        if not VOLUME_NAME.fullmatch(self.name) or self.name in {".", ".."}:
            raise ValueError("storage volume name is invalid")
        if self.volume_format not in {"qcow2", "raw"}:
            raise ValueError("storage volume format is unsupported")
        if not MIN_CAPACITY <= self.capacity_bytes <= MAX_CAPACITY:
            raise ValueError("storage volume capacity is outside the safe range")

    def encode(self) -> str:
        return json.dumps(
            vars(self),
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def decode(cls, value: str) -> "StorageVolumeCreateInput":
        if len(value) > 4_096:
            raise ValueError("storage volume input exceeds size limit")
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError("storage volume input must be an object")
            result = cls(
                host_id=str(payload["host_id"]),
                pool_resource_id=str(payload["pool_resource_id"]),
                pool_uuid=str(payload["pool_uuid"]),
                pool_generation=int(payload["pool_generation"]),
                pool_hash=str(payload["pool_hash"]),
                name=str(payload["name"]),
                volume_format=str(payload["volume_format"]),
                capacity_bytes=int(payload["capacity_bytes"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("storage volume input is invalid") from exc
        result.validate()
        return result


@dataclass(frozen=True)
class StorageVolumeMutationInput:
    host_id: str
    pool_resource_id: str
    pool_uuid: str
    pool_generation: int
    pool_hash: str
    volume_resource_id: str
    volume_native_id: str
    volume_generation: int
    volume_hash: str
    volume_key: str
    volume_name: str
    current_capacity_bytes: int
    target_capacity_bytes: int | None

    def validate(self, operation: str) -> None:
        if not self.host_id or not self.pool_resource_id or not self.volume_resource_id:
            raise ValueError("storage volume identity is invalid")
        try:
            UUID(self.pool_uuid)
        except ValueError as exc:
            raise ValueError("storage volume pool UUID is invalid") from exc
        if (
            self.pool_generation < 1
            or self.volume_generation < 1
            or not _valid_hash(self.pool_hash)
            or not _valid_hash(self.volume_hash)
        ):
            raise ValueError("storage volume base version is invalid")
        if not self.volume_native_id or not self.volume_key or not self.volume_name:
            raise ValueError("storage volume native identity is invalid")
        try:
            native_identity = json.loads(self.volume_native_id)
        except json.JSONDecodeError as exc:
            raise ValueError("storage volume native identity is invalid") from exc
        if native_identity != [self.pool_uuid, self.volume_key]:
            raise ValueError("storage volume native identity does not match key")
        if (
            not isinstance(self.current_capacity_bytes, int)
            or isinstance(self.current_capacity_bytes, bool)
            or self.current_capacity_bytes < 0
        ):
            raise ValueError("storage volume current capacity is invalid")
        if operation == "resize":
            target = self.target_capacity_bytes
            if target is None or not MIN_CAPACITY <= target <= MAX_CAPACITY:
                raise ValueError("storage volume target capacity is outside the safe range")
            if target <= self.current_capacity_bytes:
                raise ValueError("storage volume resize must increase capacity")
        elif operation == "delete":
            if self.target_capacity_bytes is not None:
                raise ValueError("storage volume delete cannot set a target capacity")
        else:
            raise ValueError("storage volume operation is unsupported")

    def encode(self) -> str:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str, operation: str) -> "StorageVolumeMutationInput":
        if len(value) > 8_192:
            raise ValueError("storage volume input exceeds size limit")
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError("storage volume input must be an object")
            result = cls(
                host_id=str(payload["host_id"]),
                pool_resource_id=str(payload["pool_resource_id"]),
                pool_uuid=str(payload["pool_uuid"]),
                pool_generation=_strict_int(payload["pool_generation"]),
                pool_hash=str(payload["pool_hash"]),
                volume_resource_id=str(payload["volume_resource_id"]),
                volume_native_id=str(payload["volume_native_id"]),
                volume_generation=_strict_int(payload["volume_generation"]),
                volume_hash=str(payload["volume_hash"]),
                volume_key=str(payload["volume_key"]),
                volume_name=str(payload["volume_name"]),
                current_capacity_bytes=_strict_int(payload["current_capacity_bytes"]),
                target_capacity_bytes=_optional_int(payload["target_capacity_bytes"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("storage volume input is invalid") from exc
        result.validate(operation)
        return result


def _valid_hash(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an integer")
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _strict_int(value)
