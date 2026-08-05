"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from nexora import __version__
from nexora.audit import DatabaseAuditSink
from nexora.auth.service import AuthService
from nexora.auth.sessions import SessionService
from nexora.config import Settings, get_settings
from nexora.consoles.serial import SerialConsoleConnector
from nexora.consoles.service import ConsoleService
from nexora.consoles.store import ConsoleSessionStore
from nexora.consoles.vnc import VncProxyManager, VncTargetService
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.capability_store import HostCapabilityStore
from nexora.hosts.connection import ManagedHostConnectionResolver
from nexora.hosts.credentials import HostCredentialService
from nexora.hosts.metrics import HostMetricsService
from nexora.hosts.onboarding import HostOnboardingService
from nexora.hosts.probe import HostProbeService
from nexora.hosts.removal import HostRemovalService
from nexora.hosts.removal_inventory import RemoteCleanupService
from nexora.hosts.removal_tasks import HostRemovalHandler
from nexora.hosts.tasks import HostCapabilityProbeHandler
from nexora.media.copy import MediaImageCopyService
from nexora.media.copy_authority import MediaCopyAuthority
from nexora.media.copy_tasks import MediaImageCopyHandler
from nexora.media.credentials import MediaCredentialService
from nexora.media.scanner import MediaScanner
from nexora.media.store import MediaIndexStore
from nexora.media.tasks import MediaScanHandler
from nexora.networking.tasks import NetworkChangeHandler
from nexora.networking.write_service import NetworkWriteService
from nexora.remote.async_ssh_backend import AsyncSSHBackend
from nexora.remote.executor import RemoteExecutor
from nexora.remote.host_key_store import HostKeyStore
from nexora.remote.relay import RemoteRelayTransfer
from nexora.remote.transfer import RemoteFileTransfer
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.domain_discovery import DomainDiscoveryService
from nexora.resources.host_network_discovery import HostNetworkDiscoveryService
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.libvirt_network_discovery import LibvirtNetworkDiscoveryService
from nexora.resources.node_device_discovery import NodeDeviceDiscoveryService
from nexora.resources.snapshot_discovery import SnapshotDiscoveryService
from nexora.resources.storage_discovery import StorageDiscoveryService
from nexora.resources.tasks import FullResourceDiscoveryHandler
from nexora.security import CredentialCipher
from nexora.security.keyring import CredentialKeyring
from nexora.storage.delete_service import StoragePoolDeleteService
from nexora.storage.lifecycle import StoragePoolLifecycleService
from nexora.storage.remote_ops import StoragePoolRemoteCommands
from nexora.storage.service import StoragePoolService
from nexora.storage.tasks import StoragePoolChangeHandler, StoragePoolLifecycleHandler
from nexora.storage.volume_mutations import StorageVolumeMutationService
from nexora.storage.volume_remote import StorageVolumeRemoteCommands
from nexora.storage.volume_service import StorageVolumeService
from nexora.storage.volume_tasks import StorageVolumeChangeHandler
from nexora.tasks.coordinator import TaskCoordinator
from nexora.tasks.locks import ResourceLockStore
from nexora.tasks.queue import TaskQueue
from nexora.vms.advanced_changes import (
    VmAdvancedDeviceChangeService,
    VmCpuTuneChangeService,
    VmNumaChangeService,
)
from nexora.vms.blank_creation_authority import VmBlankCreationAuthority
from nexora.vms.blank_creation_service import VmBlankCreationService
from nexora.vms.blank_creation_tasks import VmBlankCreationHandler
from nexora.vms.cached_iso_changes import VmCachedIsoService
from nexora.vms.cdrom_changes import VmCdromChangeService
from nexora.vms.clone_authority import VmCloneAuthority
from nexora.vms.clone_remote import VmCloneRemote
from nexora.vms.clone_service import VmCloneService
from nexora.vms.clone_tasks import VmCloneHandler
from nexora.vms.cloud_init_remote import CloudInitRemote
from nexora.vms.cpu_changes import VmCpuChangeService
from nexora.vms.creation_authority import VmCreationAuthority
from nexora.vms.creation_remote import VmCreationRemote
from nexora.vms.creation_service import VmCreationService
from nexora.vms.creation_tasks import VmCreationHandler
from nexora.vms.disk_changes import VmDiskChangeService
from nexora.vms.guest_agent import GuestAgentService
from nexora.vms.image_resize import ImageResizeRemote
from nexora.vms.lifecycle import DomainLifecycleService
from nexora.vms.media_creation_authority import VmMediaCreationAuthority
from nexora.vms.media_creation_service import VmMediaCreationService
from nexora.vms.media_creation_tasks import VmMediaCreationHandler
from nexora.vms.memory_changes import VmMemoryChangeService
from nexora.vms.metrics import VmMetricsService
from nexora.vms.metrics_sampler import MetricsSampler
from nexora.vms.network_changes import VmNetworkChangeService
from nexora.vms.peripheral_changes import VmPeripheralChangeService
from nexora.vms.platform_iso_changes import VmPlatformIsoService
from nexora.vms.remove_service import VmRemoveService
from nexora.vms.remove_tasks import VmRemoveHandler
from nexora.vms.snapshot_delete_service import SnapshotDeleteService
from nexora.vms.snapshot_revert_service import SnapshotRevertService
from nexora.vms.snapshot_service import SnapshotService
from nexora.vms.snapshot_tasks import SnapshotChangeHandler
from nexora.vms.tasks import VmAdvancedChangeHandler, VmCpuChangeHandler, VmLifecycleHandler
from nexora.web.frontend import router as frontend_router
from nexora.web.internal.router import router as internal_router
from nexora.web.middleware import SecurityHeadersMiddleware
from nexora.web.rendering import PROJECT_ROOT
from nexora.web.routes.auth import router as auth_router
from nexora.web.routes.console_socket import router as console_socket_router
from nexora.web.routes.health import router as health_router
from nexora.web.routes.media_content import router as media_content_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated Nexora application instance."""

    runtime_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        keyring = CredentialKeyring.from_settings(runtime_settings)
        app.state.credential_cipher = CredentialCipher(keyring)
        database = Database(runtime_settings)
        app.state.database = database
        app.state.auth_service = AuthService(database)
        app.state.session_service = SessionService(database)
        host_key_store = HostKeyStore(runtime_settings.data_dir / "hostkeys")
        credential_service = HostCredentialService(database, app.state.credential_cipher)
        connection_resolver = ManagedHostConnectionResolver(
            database,
            credential_service,
            host_key_store,
        )
        console_sessions = ConsoleSessionStore(database)
        serial_console = SerialConsoleConnector(database, connection_resolver)
        audit_sink = DatabaseAuditSink(database)
        remote_executor = RemoteExecutor(
            connection_resolver,
            audit_sink,
            backend=AsyncSSHBackend(),
        )
        vnc_targets = VncTargetService(database, remote_executor)
        console_service = ConsoleService(database, console_sessions, vnc_targets)
        vnc_proxy = VncProxyManager(database, connection_resolver, vnc_targets)
        remote_transfer = RemoteFileTransfer(connection_resolver, audit_sink)
        remote_relay = RemoteRelayTransfer(connection_resolver, audit_sink)
        host_probe = HostProbeService(
            database,
            remote_executor,
            HostCapabilityStore(database),
        )
        host_removal = HostRemovalService(
            database,
            RemoteCleanupService(remote_executor),
            host_key_store,
        )
        resource_store = ResourceIndexStore(database)
        resource_locks = ResourceLockStore(database)
        domain_discovery = DomainDiscoveryService(database, remote_executor, resource_store)
        vm_lifecycle = DomainLifecycleService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_cpu_changes = VmCpuChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_memory_changes = VmMemoryChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_numa_changes = VmNumaChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_cputune_changes = VmCpuTuneChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_advanced_devices = VmAdvancedDeviceChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_metrics = VmMetricsService(database, remote_executor)
        metrics_sampler = MetricsSampler(
            database,
            HostMetricsService(database, remote_executor),
            vm_metrics,
            interval_seconds=runtime_settings.metrics_sample_interval_seconds,
        )
        snapshot_discovery = SnapshotDiscoveryService(database, remote_executor, resource_store)
        vm_snapshot = SnapshotService(
            database,
            remote_executor,
            domain_discovery,
            snapshot_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_snapshot_delete = SnapshotDeleteService(
            database,
            remote_executor,
            domain_discovery,
            snapshot_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_snapshot_revert = SnapshotRevertService(
            database,
            remote_executor,
            domain_discovery,
            snapshot_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        storage_discovery = StorageDiscoveryService(database, remote_executor, resource_store)
        network_discovery = LibvirtNetworkDiscoveryService(
            database, remote_executor, resource_store
        )
        host_network_discovery = HostNetworkDiscoveryService(
            database, remote_executor, resource_store
        )
        network_write = NetworkWriteService(database, remote_executor, host_network_discovery)
        vm_creation_remote = VmCreationRemote(database, remote_executor)
        vm_creation_authority = VmCreationAuthority(
            database,
            storage_discovery,
            domain_discovery,
            host_network_discovery,
            network_discovery,
            ResourceWriteGuard(database),
            vm_creation_remote.architecture,
        )
        vm_creation = VmCreationService(
            database,
            vm_creation_authority,
            vm_creation_remote,
            domain_discovery,
            resource_store,
            resource_locks,
        )
        vm_clone_remote = VmCloneRemote(database, remote_executor)
        vm_clone = VmCloneService(
            database,
            VmCloneAuthority(
                database,
                domain_discovery,
                storage_discovery,
                vm_clone_remote,
                host_network_discovery,
                network_discovery,
            ),
            vm_clone_remote,
            remote_relay,
            domain_discovery,
            storage_discovery,
            resource_locks,
        )
        vm_disk_changes = VmDiskChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
            storage_discovery,
        )
        vm_network_changes = VmNetworkChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        vm_cdrom_changes = VmCdromChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
            storage_discovery,
        )
        storage_pool_service = StoragePoolService(
            database,
            remote_executor,
            storage_discovery,
            resource_locks,
        )
        storage_pool_lifecycle = StoragePoolLifecycleService(
            storage_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
            StoragePoolRemoteCommands(database, remote_executor),
        )
        storage_pool_delete = StoragePoolDeleteService(
            database,
            storage_discovery,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
            StoragePoolRemoteCommands(database, remote_executor),
        )
        storage_volume_service = StorageVolumeService(
            database,
            storage_discovery,
            ResourceWriteGuard(database),
            resource_locks,
            StorageVolumeRemoteCommands(database, remote_executor),
        )
        storage_volume_mutations = StorageVolumeMutationService(
            database,
            storage_discovery,
            domain_discovery,
            ResourceWriteGuard(database),
            resource_locks,
            StorageVolumeRemoteCommands(database, remote_executor),
        )
        vm_blank_creation = VmBlankCreationService(
            database,
            VmBlankCreationAuthority(
                database,
                storage_discovery,
                vm_creation_authority,
                ResourceWriteGuard(database),
                vm_creation_remote.architecture,
            ),
            vm_creation_remote,
            StorageVolumeRemoteCommands(database, remote_executor),
            resource_locks,
        )
        device_discovery = NodeDeviceDiscoveryService(database, remote_executor, resource_store)
        vm_peripheral_changes = VmPeripheralChangeService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
            device_discovery=device_discovery,
            roots=runtime_settings.shared_directory_root_list,
        )
        media_store = MediaIndexStore(database)
        media_scanner = MediaScanner(runtime_settings.library_dir, media_store)
        media_credentials = MediaCredentialService(database)
        vm_platform_iso = VmPlatformIsoService(
            runtime_settings,
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
            storage_discovery,
            media_credentials,
        )
        vm_cached_iso = VmCachedIsoService(
            runtime_settings,
            database,
            remote_executor,
            remote_transfer,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
            storage_discovery,
        )
        media_image_copy = MediaImageCopyService(
            runtime_settings.library_dir,
            remote_executor,
            remote_transfer,
            MediaCopyAuthority(
                database,
                storage_discovery,
                resource_store,
                ResourceWriteGuard(database),
                resource_locks,
            ),
        )
        vm_media_creation = VmMediaCreationService(
            database,
            VmMediaCreationAuthority(media_image_copy.authority, vm_creation_authority),
            media_image_copy,
            vm_creation_remote,
            storage_discovery,
            domain_discovery,
            resource_locks,
            CloudInitRemote(database, remote_executor),
            ImageResizeRemote(database, remote_executor),
        )
        app.state.host_key_store = host_key_store
        app.state.host_credential_service = credential_service
        app.state.host_onboarding_service = HostOnboardingService(
            database,
            app.state.credential_cipher,
            host_key_store,
        )
        app.state.remote_executor = remote_executor
        app.state.remote_file_transfer = remote_transfer
        app.state.remote_relay_transfer = remote_relay
        app.state.console_session_store = console_sessions
        app.state.console_service = console_service
        app.state.serial_console_connector = serial_console
        app.state.vnc_proxy_manager = vnc_proxy
        app.state.host_probe_service = host_probe
        app.state.host_removal_service = host_removal
        app.state.domain_discovery_service = domain_discovery
        app.state.vm_lifecycle_service = vm_lifecycle
        app.state.vm_cpu_change_service = vm_cpu_changes
        app.state.network_write_service = network_write
        app.state.vm_memory_change_service = vm_memory_changes
        app.state.vm_numa_change_service = vm_numa_changes
        app.state.vm_cputune_change_service = vm_cputune_changes
        app.state.vm_advanced_device_change_service = vm_advanced_devices
        app.state.vm_peripheral_change_service = vm_peripheral_changes
        app.state.vm_metrics_service = vm_metrics
        app.state.metrics_sampler = metrics_sampler
        app.state.vm_guest_agent_service = GuestAgentService(database, remote_executor)
        app.state.vm_creation_service = vm_creation
        app.state.vm_clone_service = vm_clone
        app.state.vm_blank_creation_service = vm_blank_creation
        vm_remove = VmRemoveService(
            database,
            remote_executor,
            domain_discovery,
            resource_store,
            ResourceWriteGuard(database),
            resource_locks,
        )
        app.state.vm_remove_service = vm_remove
        app.state.vm_media_creation_service = vm_media_creation
        app.state.vm_snapshot_service = vm_snapshot
        app.state.vm_snapshot_delete_service = vm_snapshot_delete
        app.state.vm_snapshot_revert_service = vm_snapshot_revert
        app.state.vm_disk_change_service = vm_disk_changes
        app.state.vm_network_change_service = vm_network_changes
        app.state.vm_cdrom_change_service = vm_cdrom_changes
        app.state.media_index_store = media_store
        app.state.media_credential_service = media_credentials
        app.state.vm_platform_iso_service = vm_platform_iso
        app.state.vm_cached_iso_service = vm_cached_iso
        app.state.media_image_copy_service = media_image_copy
        app.state.storage_pool_service = storage_pool_service
        app.state.storage_pool_lifecycle_service = storage_pool_lifecycle
        app.state.storage_pool_delete_service = storage_pool_delete
        app.state.storage_volume_service = storage_volume_service
        app.state.storage_volume_mutation_service = storage_volume_mutations
        task_queue = TaskQueue(database)
        coordinator = TaskCoordinator(
            task_queue,
            resource_locks=resource_locks,
            concurrency=runtime_settings.task_concurrency,
            poll_interval=runtime_settings.task_poll_interval_ms / 1_000,
            lease_seconds=runtime_settings.task_lease_seconds,
        )
        app.state.task_queue = task_queue
        app.state.task_coordinator = coordinator
        coordinator.register(
            "host.capability_probe",
            HostCapabilityProbeHandler(host_probe),
        )
        coordinator.register(
            "host.resource_discovery",
            FullResourceDiscoveryHandler(
                domain_discovery,
                snapshot_discovery,
                storage_discovery,
                network_discovery,
                host_network_discovery,
                device_discovery,
            ),
        )
        coordinator.register(
            "host.remove",
            HostRemovalHandler(host_removal),
        )
        coordinator.register(
            "vm.lifecycle",
            VmLifecycleHandler(vm_lifecycle),
        )
        coordinator.register(
            "vm.create",
            VmCreationHandler(vm_creation),
        )
        coordinator.register(
            "vm.create_blank",
            VmBlankCreationHandler(vm_blank_creation),
        )
        coordinator.register(
            "vm.remove",
            VmRemoveHandler(vm_remove),
        )
        coordinator.register(
            "vm.clone",
            VmCloneHandler(vm_clone),
        )
        coordinator.register(
            "vm.create_from_media",
            VmMediaCreationHandler(vm_media_creation),
        )
        coordinator.register(
            "vm.cpu_change",
            VmCpuChangeHandler(vm_cpu_changes),
        )
        coordinator.register(
            "vm.memory_change",
            VmCpuChangeHandler(vm_memory_changes),
        )
        coordinator.register(
            "vm.disk_change",
            VmCpuChangeHandler(vm_disk_changes),
        )
        coordinator.register(
            "vm.network_change",
            VmCpuChangeHandler(vm_network_changes),
        )
        coordinator.register(
            "vm.advanced_change",
            VmAdvancedChangeHandler(
                {
                    "numa_config": vm_numa_changes,
                    "cputune_config": vm_cputune_changes,
                    "advanced_devices": vm_advanced_devices,
                    "host_device_attach": vm_peripheral_changes,
                    "host_device_detach": vm_peripheral_changes,
                    "shared_directory_attach": vm_peripheral_changes,
                    "shared_directory_detach": vm_peripheral_changes,
                }
            ),
        )
        coordinator.register(
            "network.change",
            NetworkChangeHandler(network_write),
        )
        coordinator.register(
            "vm.cdrom_change",
            VmCpuChangeHandler(vm_cdrom_changes),
        )
        coordinator.register(
            "vm.platform_iso_change",
            VmCpuChangeHandler(vm_platform_iso),
        )
        coordinator.register(
            "vm.cached_iso_change",
            VmCpuChangeHandler(vm_cached_iso),
        )
        coordinator.register(
            "vm.snapshot_change",
            SnapshotChangeHandler(vm_snapshot, vm_snapshot_delete, vm_snapshot_revert),
        )
        coordinator.register(
            "media.scan",
            MediaScanHandler(media_scanner),
        )
        coordinator.register(
            "media.image_copy",
            MediaImageCopyHandler(media_image_copy),
        )
        coordinator.register(
            "storage.pool_change",
            StoragePoolChangeHandler(storage_pool_service, storage_pool_delete),
        )
        coordinator.register(
            "storage.pool_lifecycle",
            StoragePoolLifecycleHandler(storage_pool_lifecycle),
        )
        coordinator.register(
            "storage.volume_change",
            StorageVolumeChangeHandler(
                storage_volume_service,
                storage_volume_mutations,
            ),
        )
        try:
            upgrade_database(database)
            console_sessions.recover()
            database.check_health()
            coordinator.start()
            metrics_sampler.start()
            app.state.ready = True
            yield
        finally:
            app.state.ready = False
            await metrics_sampler.stop()
            coordinator.stop()
            await vnc_proxy.close_all()
            database.dispose()

    app = FastAPI(
        title="Nexora",
        description="Elegant virtual infrastructure management.",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.ready = False
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=runtime_settings.trusted_host_list)
    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
    app.include_router(health_router)
    app.include_router(internal_router)
    app.include_router(frontend_router)
    app.include_router(auth_router)
    app.include_router(console_socket_router)
    app.include_router(media_content_router)
    return app


app = create_app()
