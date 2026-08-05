"""Validated contracts for importing a managed volume as a VM."""

import json
import re
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import UUID, uuid4

NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class VmCreationOptions(Protocol):
    @property
    def host_id(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def vm_uuid(self) -> str: ...
    @property
    def memory_mib(self) -> int: ...
    @property
    def vcpus(self) -> int: ...
    @property
    def network_kind(self) -> str: ...
    @property
    def network_resource_id(self) -> str | None: ...
    @property
    def network_native_id(self) -> str | None: ...
    @property
    def network_generation(self) -> int | None: ...
    @property
    def network_hash(self) -> str | None: ...
    @property
    def network_name(self) -> str | None: ...

    @property
    def network_mac(self) -> str | None: ...
    @property
    def iso_resource_id(self) -> str | None: ...
    @property
    def iso_native_id(self) -> str | None: ...
    @property
    def iso_generation(self) -> int | None: ...
    @property
    def iso_hash(self) -> str | None: ...
    @property
    def iso_key(self) -> str | None: ...
    @property
    def iso_name(self) -> str | None: ...

    @property
    def disk_bus(self) -> str: ...
    @property
    def cpu_mode(self) -> str: ...
    @property
    def guest_profile(self) -> str: ...
    @property
    def firmware(self) -> str: ...
    @property
    def secure_boot(self) -> bool: ...
    @property
    def tpm2(self) -> bool: ...
    @property
    def driver_iso_resource_id(self) -> str | None: ...
    @property
    def driver_iso_native_id(self) -> str | None: ...
    @property
    def driver_iso_generation(self) -> int | None: ...
    @property
    def driver_iso_hash(self) -> str | None: ...
    @property
    def driver_iso_key(self) -> str | None: ...
    @property
    def driver_iso_name(self) -> str | None: ...


@dataclass(frozen=True)
class VmImportCreateInput:
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
    def new(cls, **values: object) -> "VmImportCreateInput":
        return cls(**values, vm_uuid=str(uuid4()))  # type: ignore[arg-type]

    def validate(self) -> None:
        identifiers = (
            self.host_id,
            self.pool_resource_id,
            self.pool_uuid,
            self.pool_hash,
            self.volume_resource_id,
            self.volume_native_id,
            self.volume_hash,
            self.volume_key,
            self.volume_name,
        )
        if not all(identifiers):
            raise ValueError("VM creation resource identity is incomplete")
        if NAME_PATTERN.fullmatch(self.name) is None:
            raise ValueError(
                "VM name must use 1-128 ASCII letters, numbers, dot, dash or underscore"
            )
        if str(UUID(self.vm_uuid)) != self.vm_uuid:
            raise ValueError("VM UUID is invalid")
        if self.pool_generation < 1 or self.volume_generation < 1:
            raise ValueError("VM creation resource generation is invalid")
        if len(self.pool_hash) != 64 or len(self.volume_hash) != 64:
            raise ValueError("VM creation resource hash is invalid")
        if not 128 <= self.memory_mib <= 1_048_576:
            raise ValueError("VM memory must be between 128 and 1048576 MiB")
        if not 1 <= self.vcpus <= 4_096:
            raise ValueError("VM vCPU count must be between 1 and 4096")
        if self.current_capacity_bytes < 1:
            raise ValueError("VM disk capacity is invalid")
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
        self._validate_network()
        self._validate_iso()
        self._validate_driver_iso()

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
                raise ValueError("VM network identity must be empty when no network is selected")
            return
        if self.network_kind not in {"bridge", "network"}:
            raise ValueError("VM network kind is invalid")
        if not all(value is not None for value in fields):
            raise ValueError("VM network identity is incomplete")
        if not isinstance(self.network_generation, int) or self.network_generation < 1:
            raise ValueError("VM network generation is invalid")
        if not isinstance(self.network_hash, str) or len(self.network_hash) != 64:
            raise ValueError("VM network hash is invalid")
        if (
            not isinstance(self.network_name, str)
            or not 1 <= len(self.network_name) <= 128
            or any(ord(character) < 32 for character in self.network_name)
        ):
            raise ValueError("VM network name is invalid")
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
        if not all(value is not None for value in fields):
            raise ValueError("VM installation ISO identity is incomplete")
        if not isinstance(self.iso_generation, int) or self.iso_generation < 1:
            raise ValueError("VM installation ISO generation is invalid")
        if not isinstance(self.iso_hash, str) or len(self.iso_hash) != 64:
            raise ValueError("VM installation ISO hash is invalid")
        if (
            not isinstance(self.iso_name, str)
            or not self.iso_name.lower().endswith(".iso")
            or len(self.iso_name) > 255
        ):
            raise ValueError("VM installation ISO name is invalid")

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
        if not all(value is not None for value in fields):
            raise ValueError("VM driver ISO identity is incomplete")
        if not isinstance(self.driver_iso_generation, int) or self.driver_iso_generation < 1:
            raise ValueError("VM driver ISO generation is invalid")
        if not isinstance(self.driver_iso_hash, str) or len(self.driver_iso_hash) != 64:
            raise ValueError("VM driver ISO hash is invalid")
        if (
            not isinstance(self.driver_iso_name, str)
            or not self.driver_iso_name.lower().endswith(".iso")
            or len(self.driver_iso_name) > 255
        ):
            raise ValueError("VM driver ISO name is invalid")

    def encode(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str) -> "VmImportCreateInput":
        if len(value) > 16_384:
            raise ValueError("VM creation input is unavailable")
        try:
            payload = json.loads(value)
            result = cls(**payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("VM creation input is invalid") from exc
        result.validate()
        return result
