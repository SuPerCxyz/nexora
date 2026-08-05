"""Validated storage task input contracts."""

import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceType


class StoragePoolAction(StrEnum):
    START = "start"
    STOP = "stop"
    REFRESH = "refresh"
    AUTOSTART_ENABLE = "autostart_enable"
    AUTOSTART_DISABLE = "autostart_disable"


@dataclass(frozen=True)
class StoragePoolLifecycleInput:
    action: StoragePoolAction
    base: ResourceBaseVersion

    def encode(self) -> str:
        return json.dumps(
            {
                "action": self.action,
                "resource_id": self.base.resource_id,
                "host_id": self.base.host_id,
                "native_id": self.base.native_id,
                "generation": self.base.generation,
                "persistent_hash": self.base.persistent_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def decode(cls, value: str | None) -> "StoragePoolLifecycleInput":
        if value is None or len(value) > 2_048:
            raise ValueError("storage lifecycle input is unavailable")
        try:
            payload = json.loads(value)
            base = ResourceBaseVersion(
                str(payload["resource_id"]),
                str(payload["host_id"]),
                ResourceType.STORAGE_POOL,
                str(UUID(str(payload["native_id"]))),
                int(payload["generation"]),
                _optional_hash(payload.get("persistent_hash")),
                None,
            )
            result = cls(StoragePoolAction(payload["action"]), base)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("storage lifecycle input is invalid") from exc
        if not base.resource_id or not base.host_id or base.generation < 1:
            raise ValueError("storage lifecycle input is invalid")
        return result


def _optional_hash(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("storage pool hash is invalid")
    return value


@dataclass(frozen=True)
class StoragePoolTaskInput:
    plan_id: str
    host_id: str
    pool_uuid: str
    operation: str

    def encode(self) -> str:
        return json.dumps(
            vars(self),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def decode(cls, value: str | None) -> "StoragePoolTaskInput":
        if value is None or len(value) > 2_048:
            raise ValueError("storage pool task input is unavailable")
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError("storage pool task input must be an object")
            result = cls(
                plan_id=str(payload["plan_id"]),
                host_id=str(payload["host_id"]),
                pool_uuid=str(UUID(str(payload["pool_uuid"]))),
                operation=str(payload["operation"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("storage pool task input is invalid") from exc
        if not result.plan_id or not result.host_id or result.operation not in {"create", "delete"}:
            raise ValueError("storage pool task input is invalid")
        return result
