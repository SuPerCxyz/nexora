"""Stable internal frontend response contracts."""

from datetime import datetime

from pydantic import BaseModel, Field


class InternalError(BaseModel):
    code: str
    message: str
    field_errors: dict[str, list[str]] = Field(default_factory=dict)
    conflict: dict[str, object] | None = None
    task_id: str | None = None


class AdministratorPreferences(BaseModel):
    username: str
    global_monospace: bool
    density: str
    language: str
    timezone: str


class InternalSession(BaseModel):
    administrator: AdministratorPreferences
    csrf_token: str
    features: dict[str, bool]


class OverviewSummary(BaseModel):
    host_total: int
    host_ready: int
    host_synced: int
    vm_total: int
    vm_running: int
    vm_paused: int
    vm_stopped: int
    active_tasks: int
    task_pending: int
    failed_tasks: int
    storage_pool_total: int
    storage_volume_total: int


class HostSummary(BaseModel):
    id: str
    name: str
    address: str
    ssh_port: int
    status: str
    labels: list[str]
    last_scanned_at: datetime | None


class VmSummary(BaseModel):
    resource_id: str
    host_id: str
    native_id: str
    name: str
    host_name: str
    state: str
    status: str
    vcpus: int | None
    memory_mib: int | None
    last_seen_at: datetime
    needs_restart: bool = False


class HostListResponse(BaseModel):
    items: list[HostSummary]
    total: int
    page: int
    page_size: int


class VmListResponse(BaseModel):
    items: list[VmSummary]
    total: int
    page: int
    page_size: int


class HostFeatureSummary(BaseModel):
    key: str
    name: str
    status: str
    description: str


class HostHardwareSummary(BaseModel):
    manufacturer: str | None
    model: str | None
    os_name: str | None
    kernel: str | None
    architecture: str | None
    cpu_model: str | None
    logical_cpus: int | None
    sockets: int | None
    cores_per_socket: int | None
    threads_per_core: int | None
    numa_nodes: int | None
    memory_bytes: int | None


class HostNetworkAdapterSummary(BaseModel):
    name: str
    mac: str | None
    kind: str
    state: str
    management: bool


class HostMetricSummary(BaseModel):
    sampled_at: datetime
    load_1: float
    load_5: float
    load_15: float
    memory_total_kib: int
    memory_available_kib: int
    uptime_seconds: int


class HostDetailResponse(BaseModel):
    host: HostSummary
    ssh_username: str
    libvirt_uri: str
    resource_counts: dict[str, int]
    virtual_machines: list[VmSummary]
    features: list[HostFeatureSummary]
    hardware: HostHardwareSummary
    network_adapters: list[HostNetworkAdapterSummary]
    latest_metrics: HostMetricSummary | None
    manage_url: str


class VmDiskSummary(BaseModel):
    type: str | None
    device: str | None
    source: str | None
    target: str | None
    bus: str | None
    format: str | None
    readonly: bool
    shareable: bool


class VmInterfaceSummary(BaseModel):
    type: str | None
    source: str | None
    mac: str | None
    target: str | None
    model: str | None


class VmHostDeviceSummary(BaseModel):
    type: str
    address: str
    category: str
    name: str
    driver: str | None
    iommu_group: str | None


class VmSnapshotSummary(BaseModel):
    resource_id: str
    name: str
    status: str
    state: str
    creation_time: str | None
    current: bool
    memory: str | None
    disks: list[str]
    xml: str | None


class VmMetricSummary(BaseModel):
    sampled_at: datetime
    state: str
    cpu_usage_percent: float | None
    memory_usage_kib: int | None
    disk_read_bytes: int | None
    disk_write_bytes: int | None
    net_rx_bytes: int | None
    net_tx_bytes: int | None


class VmDetailResponse(BaseModel):
    vm: VmSummary
    active: bool
    persistent: bool
    autostart: bool
    maximum_vcpus: int | None
    configuration_status: str
    disks: list[VmDiskSummary]
    interfaces: list[VmInterfaceSummary]
    host_devices: list[VmHostDeviceSummary]
    snapshots: list[VmSnapshotSummary]
    metrics: list[VmMetricSummary]
    xml: str
    manage_url: str


class GuestAddressSummary(BaseModel):
    interface: str
    address: str
    prefix: int
    family: str
    mac: str | None


class GuestAgentResponse(BaseModel):
    state: str
    channel_configured: bool
    hostname: str | None
    addresses: list[GuestAddressSummary]
    message: str | None


class VmCreateVolumeOption(BaseModel):
    id: str
    host_id: str
    host_name: str
    pool_name: str
    name: str
    format: str
    capacity_bytes: int


class VmCreateNetworkOption(BaseModel):
    id: str
    host_id: str
    host_name: str
    kind: str
    name: str


class VmCreateIsoOption(BaseModel):
    id: str
    host_id: str
    host_name: str
    pool_name: str
    name: str


class VmCreateOptionsResponse(BaseModel):
    volumes: list[VmCreateVolumeOption]
    networks: list[VmCreateNetworkOption]
    isos: list[VmCreateIsoOption]


class VmCreatePreviewRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    memory_mib: int = Field(ge=128, le=1_048_576)
    vcpus: int = Field(ge=1, le=4_096)
    volume_resource_id: str
    network_resource_id: str = ""
    iso_resource_id: str = ""
    driver_iso_resource_id: str = ""
    disk_bus: str = "virtio"
    cpu_mode: str = "host-model"
    guest_profile: str = "linux"
    firmware: str = "bios"
    secure_boot: bool = False
    tpm2: bool = False


class VmCreatePreviewSummary(BaseModel):
    name: str
    host_name: str
    vcpus: int
    memory_mib: int
    volume_name: str
    network: str
    iso_name: str | None
    firmware: str
    secure_boot: bool
    tpm2: bool


class VmCreatePreviewResponse(BaseModel):
    plan_id: str
    confirmation_token: str
    host_id: str
    vm_uuid: str
    diff_text: str
    summary: VmCreatePreviewSummary


class VmCreateApplyRequest(BaseModel):
    plan_id: str
    confirmation_token: str
    host_id: str
    vm_uuid: str


class VmBlankCreatePoolOption(BaseModel):
    id: str
    host_id: str
    host_name: str
    pool_name: str
    target_path: str


class VmBlankCreateOptionsResponse(BaseModel):
    pools: list[VmBlankCreatePoolOption]
    networks: list[VmCreateNetworkOption]
    isos: list[VmCreateIsoOption]


class VmBlankCreatePreviewRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    memory_mib: int = Field(ge=128, le=1_048_576)
    vcpus: int = Field(ge=1, le=4_096)
    pool_resource_id: str
    disk_name: str = Field(min_length=1, max_length=255)
    volume_format: str = "qcow2"
    capacity_gib: int = Field(ge=1, le=8192)
    network_resource_id: str = ""
    iso_resource_id: str = ""
    driver_iso_resource_id: str = ""
    disk_bus: str = "virtio"
    cpu_mode: str = "host-model"
    guest_profile: str = "linux"
    firmware: str = "bios"
    secure_boot: bool = False
    tpm2: bool = False


class VmBlankCreatePreviewSummary(BaseModel):
    name: str
    host_name: str
    vcpus: int
    memory_mib: int
    pool_name: str
    disk_name: str
    volume_format: str
    capacity_bytes: int
    network: str
    iso_name: str | None
    firmware: str
    secure_boot: bool
    tpm2: bool


class VmBlankCreatePreviewResponse(BaseModel):
    plan_id: str
    confirmation_token: str
    host_id: str
    vm_uuid: str
    diff_text: str
    summary: VmBlankCreatePreviewSummary


class TaskCreatedResponse(BaseModel):
    task_id: str
    location: str


class HostOnboardingRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    address: str = Field(min_length=1, max_length=255)
    ssh_port: int = Field(ge=1, le=65_535)
    ssh_username: str = Field(min_length=1, max_length=64)
    authentication_method: str
    password: str | None = None
    private_key: str | None = None
    private_key_passphrase: str | None = None
    sudo_mode: str
    labels: list[str] = Field(default_factory=list, max_length=32)
    notes: str | None = Field(default=None, max_length=4_000)


class HostKeySummary(BaseModel):
    key_type: str
    fingerprint: str


class HostOnboardingStartedResponse(BaseModel):
    host_id: str
    location: str


class HostKeyConfirmationResponse(BaseModel):
    host_id: str
    name: str
    endpoint: str
    host_key_digest: str
    fingerprints: list[HostKeySummary]


class HostKeyConfirmRequest(BaseModel):
    host_key_digest: str


class VmMediaOption(BaseModel):
    id: str
    file_name: str
    format: str
    size_bytes: int
    virtual_size_bytes: int | None


class VmMediaTargetOption(BaseModel):
    id: str
    host_id: str
    host_name: str
    pool_name: str
    target_path: str


class VmMediaCreateOptionsResponse(BaseModel):
    media: list[VmMediaOption]
    targets: list[VmMediaTargetOption]
    networks: list[VmCreateNetworkOption]
    isos: list[VmCreateIsoOption]


class VmMediaCreatePreviewRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    memory_mib: int = Field(ge=128, le=1_048_576)
    vcpus: int = Field(ge=1, le=4_096)
    media_item_id: str
    pool_resource_id: str
    target_file_name: str = Field(min_length=1, max_length=255)
    target_capacity_gib: int | None = Field(default=None, ge=1, le=16_384)
    network_resource_id: str = ""
    iso_resource_id: str = ""
    driver_iso_resource_id: str = ""
    disk_bus: str = "virtio"
    cpu_mode: str = "host-model"
    guest_profile: str = "linux"
    firmware: str = "bios"
    secure_boot: bool = False
    tpm2: bool = False
    cloud_init: bool = False
    cloud_hostname: str = ""
    cloud_username: str = ""
    cloud_ssh_public_key: str = ""
    cloud_password: str = ""
    cloud_password_confirmation: str = ""
    cloud_network_mode: str = "dhcp"
    cloud_ipv4_cidr: str = ""
    cloud_ipv4_gateway: str = ""
    cloud_ipv6_cidr: str = ""
    cloud_ipv6_gateway: str = ""
    cloud_dns_addresses: list[str] = Field(default_factory=list, max_length=3)


class VmMediaCreatePreviewSummary(BaseModel):
    name: str
    host_name: str
    media_name: str
    pool_name: str
    target_path: str
    source_sha256: str
    vcpus: int
    memory_mib: int
    target_capacity_bytes: int | None
    network: str
    iso_name: str | None
    driver_iso_name: str | None
    firmware: str
    secure_boot: bool
    tpm2: bool
    cloud_init: str | None


class VmMediaCreatePreviewResponse(BaseModel):
    plan_id: str
    confirmation_token: str
    host_id: str
    vm_uuid: str
    diff_text: str
    summary: VmMediaCreatePreviewSummary
