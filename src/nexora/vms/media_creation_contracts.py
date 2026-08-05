"""Persistent input for copying one platform image and defining a VM."""

import json
import re
from dataclasses import asdict, dataclass
from ipaddress import (
    IPv4Address,
    IPv4Interface,
    IPv6Address,
    IPv6Interface,
    ip_address,
    ip_interface,
)
from uuid import UUID, uuid4

from nexora.media.copy_contracts import COPY_NAME
from nexora.vms.creation_contracts import NAME_PATTERN


@dataclass(frozen=True)
class VmMediaCreateInput:
    media_item_id: str
    media_sha256: str
    media_format: str
    host_id: str
    pool_resource_id: str
    pool_uuid: str
    pool_generation: int
    pool_hash: str
    target_file_name: str
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
    cloud_hostname: str | None = None
    cloud_username: str | None = None
    cloud_ssh_public_key: str | None = None
    cloud_password_hash: str | None = None
    cloud_network_mode: str | None = None
    cloud_ipv4_cidr: str | None = None
    cloud_ipv4_gateway: str | None = None
    cloud_ipv6_cidr: str | None = None
    cloud_ipv6_gateway: str | None = None
    cloud_dns_addresses: tuple[str, ...] = ()
    source_virtual_size_bytes: int | None = None
    target_capacity_bytes: int | None = None
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
    def new(cls, **values: object) -> "VmMediaCreateInput":
        return cls(**values, vm_uuid=str(uuid4()))  # type: ignore[arg-type]

    def validate(self) -> None:
        if not all(
            (
                self.media_item_id,
                self.media_sha256,
                self.host_id,
                self.pool_resource_id,
                self.pool_uuid,
                self.pool_hash,
            )
        ):
            raise ValueError("platform image VM resource identity is incomplete")
        if self.media_format not in {"qcow2", "raw"}:
            raise ValueError("platform image format is unsupported")
        if (
            len(self.media_sha256) != 64
            or self.pool_generation < 1
            or len(self.pool_hash) != 64
            or COPY_NAME.fullmatch(self.target_file_name) is None
            or not self.target_file_name.endswith(f".{self.media_format}")
        ):
            raise ValueError("platform image or target identity is invalid")
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
        self._validate_cloud_init()
        self._validate_capacity()

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

    def _validate_cloud_init(self) -> None:
        identity = (self.cloud_hostname, self.cloud_username)
        options = (
            self.cloud_ssh_public_key,
            self.cloud_password_hash,
            self.cloud_network_mode,
            self.cloud_ipv4_cidr,
            self.cloud_ipv4_gateway,
            self.cloud_ipv6_cidr,
            self.cloud_ipv6_gateway,
            *self.cloud_dns_addresses,
        )
        if all(value is None for value in identity) and not any(options):
            return
        if not all(isinstance(value, str) and value for value in identity):
            raise ValueError("cloud-init identity is incomplete")
        assert self.cloud_hostname is not None
        assert self.cloud_username is not None
        if (
            len(self.cloud_hostname) > 253
            or re.fullmatch(
                r"(?i)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9]"
                r"(?:[a-z0-9-]{0,61}[a-z0-9])?)*",
                self.cloud_hostname,
            )
            is None
            or re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", self.cloud_username) is None
        ):
            raise ValueError("cloud-init hostname or username is invalid")
        self._validate_cloud_access()
        self._validate_cloud_network()
        if self.network_kind == "none" or self.network_mac is None:
            raise ValueError("cloud-init requires a selected network and planned MAC")

    def _validate_cloud_access(self) -> None:
        allowed = ("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-nistp")
        if self.cloud_ssh_public_key is not None and (
            not self.cloud_ssh_public_key.startswith(allowed)
            or len(self.cloud_ssh_public_key) > 16_384
        ):
            raise ValueError("cloud-init SSH public key is invalid")
        if self.cloud_password_hash is not None and (
            not self.cloud_password_hash.startswith("$6$") or len(self.cloud_password_hash) > 256
        ):
            raise ValueError("cloud-init password hash is invalid")
        if self.cloud_ssh_public_key is None and self.cloud_password_hash is None:
            raise ValueError("cloud-init requires an SSH public key or password")

    def _validate_cloud_network(self) -> None:
        if self.cloud_network_mode == "dhcp":
            if (
                self.cloud_ipv4_cidr is not None
                or self.cloud_ipv4_gateway is not None
                or self.cloud_ipv6_cidr is not None
                or self.cloud_ipv6_gateway is not None
                or self.cloud_dns_addresses
            ):
                raise ValueError("cloud-init DHCP cannot include static network fields")
            return
        if self.cloud_network_mode != "static":
            raise ValueError("cloud-init network mode is invalid")
        if self.cloud_ipv4_cidr is None and self.cloud_ipv6_cidr is None:
            raise ValueError("cloud-init static network requires an address")
        if (self.cloud_ipv4_cidr is None) != (self.cloud_ipv4_gateway is None):
            raise ValueError("cloud-init static IPv4 fields are incomplete")
        if (self.cloud_ipv6_cidr is None) != (self.cloud_ipv6_gateway is None):
            raise ValueError("cloud-init static IPv6 fields are incomplete")
        if self.cloud_ipv4_cidr is not None:
            interface = _static_interface(self.cloud_ipv4_cidr)
            gateway = _ipv4_address(self.cloud_ipv4_gateway, "gateway")
            if gateway not in interface.network or gateway == interface.ip:
                raise ValueError("cloud-init gateway is outside the selected subnet")
        if self.cloud_ipv6_cidr is not None:
            interface6 = _static_interface6(self.cloud_ipv6_cidr)
            gateway6 = _ipv6_address(self.cloud_ipv6_gateway, "IPv6 gateway")
            if gateway6 not in interface6.network or gateway6 == interface6.ip:
                raise ValueError("cloud-init IPv6 gateway is outside the selected subnet")
        if not 1 <= len(self.cloud_dns_addresses) <= 3:
            raise ValueError("cloud-init static DNS count is invalid")
        if len(self.cloud_dns_addresses) != len(set(self.cloud_dns_addresses)):
            raise ValueError("cloud-init DNS addresses contain duplicates")
        for value in self.cloud_dns_addresses:
            address = ip_address(value)
            if address.is_unspecified or address.is_multicast:
                raise ValueError("cloud-init DNS address is invalid")

    def _validate_capacity(self) -> None:
        if self.target_capacity_bytes is None:
            return
        if (
            self.source_virtual_size_bytes is None
            or self.source_virtual_size_bytes < 1
            or self.target_capacity_bytes < self.source_virtual_size_bytes
            or self.target_capacity_bytes > 16 * 1024**4
        ):
            raise ValueError("target image capacity is invalid")

    def encode(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str) -> "VmMediaCreateInput":
        if len(value) > 16_384:
            raise ValueError("platform image VM input is unavailable")
        try:
            payload = json.loads(value)
            payload["cloud_dns_addresses"] = tuple(payload.get("cloud_dns_addresses", ()))
            result = cls(**payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("platform image VM input is invalid") from exc
        result.validate()
        return result


def _static_interface(value: str | None) -> IPv4Interface:
    try:
        interface = ip_interface(value or "")
    except ValueError as exc:
        raise ValueError("cloud-init static IPv4 CIDR is invalid") from exc
    if (
        not isinstance(interface, IPv4Interface)
        or interface.ip.is_unspecified
        or interface.ip.is_loopback
        or interface.ip.is_link_local
        or interface.ip.is_multicast
    ):
        raise ValueError("cloud-init static IPv4 CIDR is invalid")
    return interface


def _ipv4_address(value: str | None, label: str) -> IPv4Address:
    try:
        address = ip_address(value or "")
    except ValueError as exc:
        raise ValueError(f"cloud-init {label} is invalid") from exc
    if (
        not isinstance(address, IPv4Address)
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
    ):
        raise ValueError(f"cloud-init {label} is invalid")
    return address


def _static_interface6(value: str | None) -> IPv6Interface:
    try:
        interface = ip_interface(value or "")
    except ValueError as exc:
        raise ValueError("cloud-init static IPv6 CIDR is invalid") from exc
    if not isinstance(interface, IPv6Interface) or _invalid_address(interface.ip):
        raise ValueError("cloud-init static IPv6 CIDR is invalid")
    return interface


def _ipv6_address(value: str | None, label: str) -> IPv6Address:
    try:
        address = ip_address(value or "")
    except ValueError as exc:
        raise ValueError(f"cloud-init {label} is invalid") from exc
    if not isinstance(address, IPv6Address) or _invalid_address(address):
        raise ValueError(f"cloud-init {label} is invalid")
    return address


def _invalid_address(address: IPv4Address | IPv6Address) -> bool:
    return (
        address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
    )
