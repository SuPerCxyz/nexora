"""Validated input for creating a blank disk volume and a VM in one task."""

import json
import re
from dataclasses import asdict, dataclass
from uuid import UUID, uuid4

from nexora.storage.volume_contracts import VOLUME_NAME
from nexora.vms.creation_contracts import NAME_PATTERN


@dataclass(frozen=True)
class VmBlankCreateInput:
    host_id: str
    pool_resource_id: str
    pool_uuid: str
    pool_generation: int
    pool_hash: str
    disk_name: str
    volume_format: str
    capacity_bytes: int
    name: str
    memory_mib: int
    vcpus: int
    vm_uuid: str
    network_kind: str = "none"
    network_resource_id: str | None = None
    network_native_id: str | None = None
    network_generation: int | None = None
    network_hash: str | None = None
    network_name: str | None = None
    network_mac: str | None = None
    iso_resource_id: str | None = None
    iso_native_id: str | None = None
    iso_generation: int | None = None
    iso_hash: str | None = None
    iso_key: str | None = None
    iso_name: str | None = None
    disk_bus: str = "virtio"
    cpu_mode: str = "host-model"
    guest_profile: str = "linux"
    firmware: str = "bios"
    secure_boot: bool = False
    tpm2: bool = False
    driver_iso_resource_id: str | None = None
    driver_iso_native_id: str | None = None
    driver_iso_generation: int | None = None
    driver_iso_hash: str | None = None
    driver_iso_key: str | None = None
    driver_iso_name: str | None = None

    @classmethod
    def new(cls, **values: object) -> "VmBlankCreateInput":
        return cls(**values, vm_uuid=str(uuid4()))  # type: ignore[arg-type]

    def validate(self) -> None:
        if not all(
            (
                self.host_id,
                self.pool_resource_id,
                self.pool_uuid,
                self.pool_hash,
                self.disk_name,
            )
        ):
            raise ValueError("blank disk VM resource identity is incomplete")
        if self.pool_generation < 1 or len(self.pool_hash) != 64:
            raise ValueError("blank disk VM pool version is invalid")
        if VOLUME_NAME.fullmatch(self.disk_name) is None or self.disk_name in {".", ".."}:
            raise ValueError("blank disk name is invalid")
        if self.volume_format not in {"qcow2", "raw"}:
            raise ValueError("blank disk format is unsupported")
        if not 1024 * 1024 <= self.capacity_bytes <= 8 * 1024**5:
            raise ValueError("blank disk capacity is outside the safe range")
        if NAME_PATTERN.fullmatch(self.name) is None:
            raise ValueError("VM name is invalid")
        if str(UUID(self.vm_uuid)) != self.vm_uuid:
            raise ValueError("VM UUID is invalid")
        if not 128 <= self.memory_mib <= 1_048_576 or not 1 <= self.vcpus <= 4_096:
            raise ValueError("VM CPU or memory is invalid")
        self._validate_network()
        self._validate_iso()
        self._validate_driver_iso()
        self._validate_platform_options()

    def _validate_network(self) -> None:
        fields = (
            self.network_resource_id,
            self.network_native_id,
            self.network_generation,
            self.network_hash,
            self.network_name,
        )
        if self.network_kind == "none":
            if any(value is not None for value in (*fields, self.network_mac)):
                raise ValueError("VM network identity must be empty")
            return
        if self.network_kind not in {"bridge", "network"} or not all(
            value is not None for value in fields
        ):
            raise ValueError("VM network identity is invalid")
        if int(self.network_generation or 0) < 1 or len(str(self.network_hash)) != 64:
            raise ValueError("VM network version is invalid")
        if (
            self.network_mac is not None
            and re.fullmatch(r"(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}", self.network_mac) is None
        ):
            raise ValueError("VM network MAC is invalid")

    def _validate_iso(self) -> None:
        fields = (
            self.iso_resource_id,
            self.iso_native_id,
            self.iso_generation,
            self.iso_hash,
            self.iso_key,
            self.iso_name,
        )
        if all(value is None for value in fields):
            return
        if (
            not all(value is not None for value in fields)
            or int(self.iso_generation or 0) < 1
            or len(str(self.iso_hash)) != 64
            or not str(self.iso_name).lower().endswith(".iso")
        ):
            raise ValueError("VM installation ISO identity is invalid")

    def _validate_driver_iso(self) -> None:
        fields = (
            self.driver_iso_resource_id,
            self.driver_iso_native_id,
            self.driver_iso_generation,
            self.driver_iso_hash,
            self.driver_iso_key,
            self.driver_iso_name,
        )
        if all(value is None for value in fields):
            return
        if (
            not all(value is not None for value in fields)
            or int(self.driver_iso_generation or 0) < 1
            or len(str(self.driver_iso_hash)) != 64
            or not str(self.driver_iso_name).lower().endswith(".iso")
        ):
            raise ValueError("VM driver ISO identity is invalid")

    def _validate_platform_options(self) -> None:
        if self.disk_bus not in {"virtio", "sata", "scsi"}:
            raise ValueError("VM disk bus is unsupported")
        if self.cpu_mode not in {"host-model", "host-passthrough"}:
            raise ValueError("VM CPU mode is unsupported")
        if self.guest_profile not in {"linux", "windows"}:
            raise ValueError("VM guest profile is unsupported")
        if self.firmware not in {"bios", "uefi"}:
            raise ValueError("VM firmware is unsupported")
        if self.secure_boot and self.firmware != "uefi":
            raise ValueError("Secure Boot requires UEFI firmware")

    def encode(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str) -> "VmBlankCreateInput":
        if len(value) > 16_384:
            raise ValueError("blank disk VM input is unavailable")
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError("blank disk VM input must be an object")
            result = cls(**payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("blank disk VM input is invalid") from exc
        result.validate()
        return result
