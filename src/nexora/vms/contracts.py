"""Validated VM lifecycle task contracts."""

import json
from dataclasses import dataclass
from enum import StrEnum

from nexora.resources.conflicts import ResourceBaseVersion
from nexora.resources.models import ResourceType


class LifecycleAction(StrEnum):
    START = "start"
    SHUTDOWN = "shutdown"
    FORCE_OFF = "force_off"
    REBOOT = "reboot"
    FORCE_REBOOT = "force_reboot"
    PAUSE = "pause"
    RESUME = "resume"
    MANAGED_SAVE = "managed_save"
    AUTOSTART_ENABLE = "autostart_enable"
    AUTOSTART_DISABLE = "autostart_disable"


@dataclass(frozen=True)
class LifecycleTaskInput:
    action: LifecycleAction
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
                "live_hash": self.base.live_hash,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def decode(cls, value: str | None) -> "LifecycleTaskInput":
        if value is None or len(value) > 4_096:
            raise ValueError("VM lifecycle task input is unavailable")
        try:
            payload = json.loads(value)
            action = LifecycleAction(payload["action"])
            base = ResourceBaseVersion(
                resource_id=str(payload["resource_id"]),
                host_id=str(payload["host_id"]),
                resource_type=ResourceType.VIRTUAL_MACHINE,
                native_id=str(payload["native_id"]),
                generation=int(payload["generation"]),
                persistent_hash=_optional_text(payload.get("persistent_hash")),
                live_hash=_optional_text(payload.get("live_hash")),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("VM lifecycle task input is invalid") from exc
        if not base.resource_id or not base.host_id or not base.native_id or base.generation < 1:
            raise ValueError("VM lifecycle task input is invalid")
        return cls(action, base)


@dataclass(frozen=True)
class VmChangeTaskInput:
    plan_id: str
    host_id: str
    vm_uuid: str
    change_type: str

    def encode(self) -> str:
        return json.dumps(
            {
                "plan_id": self.plan_id,
                "host_id": self.host_id,
                "vm_uuid": self.vm_uuid,
                "change_type": self.change_type,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def decode(cls, value: str | None) -> "VmChangeTaskInput":
        if value is None or len(value) > 1_024:
            raise ValueError("VM change task input is unavailable")
        try:
            payload = json.loads(value)
            task_input = cls(
                str(payload["plan_id"]),
                str(payload["host_id"]),
                str(payload["vm_uuid"]),
                str(payload["change_type"]),
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("VM change task input is invalid") from exc
        if not all(
            (
                task_input.plan_id,
                task_input.host_id,
                task_input.vm_uuid,
                task_input.change_type,
            )
        ):
            raise ValueError("VM change task input is invalid")
        return task_input


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("invalid VM lifecycle hash")
    return value
