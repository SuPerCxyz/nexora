"""Typed host capability observations."""

from dataclasses import dataclass
from enum import StrEnum

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class CapabilityStatus(StrEnum):
    NORMAL = "normal"
    REQUIRED_MISSING = "required_missing"
    OPTIONAL_MISSING = "optional_missing"
    PERMISSION_DENIED = "permission_denied"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CapabilityObservation:
    key: str
    status: CapabilityStatus
    value: JsonValue | None = None
    detail: str | None = None


@dataclass(frozen=True)
class HostProbeReport:
    host_id: str
    observations: tuple[CapabilityObservation, ...]

    @property
    def healthy(self) -> bool:
        blocking = {
            CapabilityStatus.REQUIRED_MISSING,
            CapabilityStatus.PERMISSION_DENIED,
            CapabilityStatus.UNSUPPORTED,
            CapabilityStatus.UNKNOWN,
        }
        required_keys = {
            "system.identity",
            "system.sudo",
            "tool.virsh",
            "libvirt.version",
            "libvirt.nodeinfo",
        }
        return not any(
            item.key in required_keys and item.status in blocking for item in self.observations
        )
