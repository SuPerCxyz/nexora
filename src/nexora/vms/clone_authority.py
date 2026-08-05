"""Authoritative preflight and immutable manifest generation for VM clones."""

import json
import secrets
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import select

from nexora.db import Database
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.host_network_discovery import HostNetworkDiscoveryService
from nexora.resources.libvirt_network_discovery import LibvirtNetworkDiscoveryService
from nexora.resources.models import ResourceDocument, ResourceIndex, ResourceStatus, ResourceType
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.vms.clone_contracts import CloneFile, VmCloneManifest
from nexora.vms.clone_remote import VmCloneRemote


class VmCloneConflict(RuntimeError):
    pass


class VmCloneAuthority:
    def __init__(
        self,
        database: Database,
        domains: DomainDiscoveryService,
        storage: StorageDiscoveryService,
        remote: VmCloneRemote,
        host_networks: HostNetworkDiscoveryService,
        libvirt_networks: LibvirtNetworkDiscoveryService,
    ) -> None:
        self.database = database
        self.domains = domains
        self.storage = storage
        self.remote = remote
        self.host_networks = host_networks
        self.libvirt_networks = libvirt_networks

    def build_manifest(
        self,
        *,
        source_host_id: str,
        source_vm_uuid: str,
        source_resource_id: str,
        source_generation: int,
        source_hash: str,
        target_pool_id: str,
        target_name: str,
        plan_id: str,
        preserve_identity: bool = False,
    ) -> tuple[VmCloneManifest, bytes]:
        UUID(plan_id)
        self.domains.run(source_host_id)
        source, source_xml = self._source(source_resource_id, source_host_id, source_vm_uuid)
        self._verify_source(source, source_generation, source_hash)
        pool = self._pool(target_pool_id)
        self.storage.run(pool.host_id)
        pool = self._pool(target_pool_id)
        pool_details = json.loads(pool.details_json)
        target_dir = _target_directory(pool, pool_details)
        details = json.loads(source.details_json)
        self.verify_target_networks(pool.host_id, source_xml)
        files, _ = self._files(
            source_host_id,
            pool.host_id,
            source_xml,
            target_dir,
            target_name,
            plan_id,
        )
        self._verify_unshared_files(source_host_id, source_vm_uuid, files)
        _verify_capacity(pool_details, files)
        if preserve_identity:
            target_uuid = source_vm_uuid
            mac_addresses = tuple(
                str(item.get("mac"))
                for item in details.get("interfaces", [])
                if isinstance(item, dict) and item.get("mac")
            )
            if len(mac_addresses) != len(details.get("interfaces", [])):
                raise VmCloneConflict("migration requires every interface to have a MAC")
            target_name = source.display_name
        else:
            target_uuid = str(uuid4())
            mac_addresses = tuple(_new_mac() for _ in details.get("interfaces", []))
        manifest = VmCloneManifest(
            source_host_id=source_host_id,
            source_vm_uuid=source_vm_uuid,
            source_generation=source.observed_generation,
            source_hash=str(source.persistent_hash),
            target_host_id=pool.host_id,
            target_pool_id=pool.id,
            target_pool_uuid=pool.native_id,
            target_pool_generation=pool.observed_generation,
            target_pool_hash=str(pool.persistent_hash),
            target_vm_uuid=target_uuid,
            target_name=target_name,
            mac_addresses=mac_addresses,
            files=tuple(files),
            preserve_identity=preserve_identity,
        )
        manifest.validate()
        return manifest, source_xml

    def verify_target_networks(self, target_host_id: str, source_xml: bytes) -> None:
        from nexora.xml import LibvirtXmlDocument

        document = LibvirtXmlDocument.parse(source_xml, expected_root="domain")
        requirements: list[tuple[ResourceType, str]] = []
        for interface in document.root.findall("./devices/interface"):
            kind = interface.get("type")
            source = interface.find("source")
            if kind == "bridge" and source is not None and source.get("bridge"):
                requirements.append((ResourceType.HOST_INTERFACE, str(source.get("bridge"))))
            elif kind == "network" and source is not None and source.get("network"):
                requirements.append((ResourceType.LIBVIRT_NETWORK, str(source.get("network"))))
            elif kind not in {"user"}:
                raise VmCloneConflict("source VM network type is not clone-compatible")
        if any(kind == ResourceType.HOST_INTERFACE for kind, _ in requirements):
            self.host_networks.run(target_host_id)
        if any(kind == ResourceType.LIBVIRT_NETWORK for kind, _ in requirements):
            self.libvirt_networks.run(target_host_id)
        with self.database.session() as session:
            for resource_type, name in requirements:
                match = session.scalar(
                    select(ResourceIndex).where(
                        ResourceIndex.host_id == target_host_id,
                        ResourceIndex.resource_type == resource_type,
                        ResourceIndex.display_name == name,
                        ResourceIndex.status != ResourceStatus.MISSING,
                    )
                )
                if match is None:
                    raise VmCloneConflict(f"target host is missing required network {name}")

    def _source(
        self,
        resource_id: str,
        host_id: str,
        vm_uuid: str,
    ) -> tuple[ResourceIndex, bytes]:
        with self.database.session() as session:
            source = session.get(ResourceIndex, resource_id)
            document = session.scalar(
                select(ResourceDocument).where(
                    ResourceDocument.resource_index_id == resource_id,
                    ResourceDocument.document_kind == "persistent_xml",
                )
            )
            if source is None or document is None:
                raise VmCloneConflict("source VM or persistent XML is unavailable")
            session.expunge(source)
            return source, document.content

    def _verify_source(self, source: ResourceIndex, generation: int, digest: str) -> None:
        details = json.loads(source.details_json)
        if (
            source.resource_type != ResourceType.VIRTUAL_MACHINE
            or source.status != ResourceStatus.MANAGED
            or source.observed_generation < generation
            or source.persistent_hash != digest
            or not details.get("persistent")
            or details.get("active")
            or details.get("managed_save")
            or details.get("host_devices")
        ):
            raise VmCloneConflict("source VM changed or is not safe to clone while shut off")

    def _files(
        self,
        source_host_id: str,
        target_host_id: str,
        source_xml: bytes,
        target_dir: PurePosixPath,
        target_name: str,
        plan_id: str,
    ) -> tuple[list[CloneFile], dict[str, str]]:
        from nexora.xml import LibvirtXmlDocument

        document = LibvirtXmlDocument.parse(source_xml, expected_root="domain")
        files: list[CloneFile] = []
        path_map: dict[str, str] = {}
        for index, disk in enumerate(document.root.findall("./devices/disk")):
            if disk.get("device") != "disk":
                source = disk.find("source")
                if source_host_id != target_host_id and source is not None and source.get("file"):
                    raise VmCloneConflict(
                        "cross-host clone requires removable file media to be ejected"
                    )
                continue
            source = disk.find("source")
            driver = disk.find("driver")
            path = source.get("file") if source is not None else None
            if (
                disk.get("type") != "file"
                or path is None
                or driver is None
                or driver.get("type") not in {"qcow2", "raw"}
                or disk.find("readonly") is not None
                or disk.find("shareable") is not None
            ):
                raise VmCloneConflict("source has an unsupported or shared writable disk")
            info = self.remote.inspect_source(source_host_id, path, disk=True)
            extension = "qcow2" if info.format == "qcow2" else "raw"
            target = target_dir / f"{target_name}-disk{index + 1}.{extension}"
            partial = target_dir / f".{target.name}.nexora-{plan_id}.partial"
            files.append(CloneFile(path, str(target), str(partial), info.size_bytes, "disk"))
            path_map[path] = str(target)
        nvram = document.root.findtext("./os/nvram")
        if nvram:
            info = self.remote.inspect_source(source_host_id, nvram, disk=False)
            target = target_dir / f"{target_name}_VARS.fd"
            partial = target_dir / f".{target.name}.nexora-{plan_id}.partial"
            files.append(CloneFile(nvram, str(target), str(partial), info.size_bytes, "nvram"))
            path_map[nvram] = str(target)
        if not files:
            raise VmCloneConflict("source VM has no cloneable file disk")
        if len(path_map) != len(files):
            raise VmCloneConflict("source VM references a file more than once")
        return files, path_map

    def _pool(self, resource_id: str) -> ResourceIndex:
        with self.database.session() as session:
            pool = session.get(ResourceIndex, resource_id)
            if pool is None:
                raise VmCloneConflict("target storage pool is unavailable")
            session.expunge(pool)
            return pool

    def _verify_unshared_files(
        self,
        host_id: str,
        source_vm_uuid: str,
        files: list[CloneFile],
    ) -> None:
        disk_paths = {item.source_path for item in files if item.kind == "disk"}
        with self.database.session() as session:
            peers = list(
                session.scalars(
                    select(ResourceIndex).where(
                        ResourceIndex.host_id == host_id,
                        ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                        ResourceIndex.native_id != source_vm_uuid,
                        ResourceIndex.status != ResourceStatus.MISSING,
                    )
                )
            )
        for peer in peers:
            details = json.loads(peer.details_json)
            referenced = {
                item.get("source") for item in details.get("disks", []) if isinstance(item, dict)
            }
            if disk_paths & referenced:
                raise VmCloneConflict(f"source disk is also referenced by VM {peer.display_name}")


def _target_directory(
    pool: ResourceIndex,
    details: dict[str, object],
) -> PurePosixPath:
    value = details.get("target_path")
    path = PurePosixPath(value) if isinstance(value, str) else PurePosixPath(".")
    if (
        pool.status != ResourceStatus.MANAGED
        or details.get("pool_type") not in {"dir", "netfs"}
        or not details.get("active")
        or not path.is_absolute()
        or ".." in path.parts
    ):
        raise VmCloneConflict("target pool is not active, writable, and path-safe")
    return path


def _verify_capacity(details: dict[str, object], files: list[CloneFile]) -> None:
    available = details.get("available_bytes")
    if (
        isinstance(available, int)
        and not isinstance(available, bool)
        and sum(item.size_bytes for item in files) > available
    ):
        raise VmCloneConflict("target storage pool does not have enough free space")


def _new_mac() -> str:
    suffix = secrets.token_bytes(3)
    return "52:54:00:" + ":".join(f"{value:02x}" for value in suffix)
