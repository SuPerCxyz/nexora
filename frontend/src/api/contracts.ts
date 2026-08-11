export type AdministratorPreferences = {
  username: string;
  global_monospace: boolean;
  density: string;
  language: string;
  timezone: string;
};

export type InternalSession = {
  administrator: AdministratorPreferences;
  csrf_token: string;
  features: Record<string, boolean>;
};

export type InternalErrorPayload = {
  code: string;
  message: string;
  field_errors: Record<string, string[]>;
  conflict: Record<string, unknown> | null;
  task_id: string | null;
};

export type OverviewSummary = {
  host_total: number;
  host_ready: number;
  host_synced: number;
  vm_total: number;
  vm_running: number;
  vm_paused: number;
  vm_stopped: number;
  active_tasks: number;
  task_pending: number;
  failed_tasks: number;
  storage_pool_total: number;
  storage_volume_total: number;
};

export type HostSummary = {
  id: string;
  name: string;
  address: string;
  ssh_port: number;
  status: string;
  labels: string[];
  last_scanned_at: string | null;
};

export type VmSummary = {
  resource_id: string;
  host_id: string;
  native_id: string;
  name: string;
  host_name: string;
  state: string;
  status: string;
  vcpus: number | null;
  memory_mib: number | null;
  last_seen_at: string;
  needs_restart: boolean;
};

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type HostFeatureSummary = {
  key: string;
  name: string;
  status: string;
  description: string;
};

export type HostHardwareSummary = {
  manufacturer: string | null;
  model: string | null;
  os_name: string | null;
  kernel: string | null;
  architecture: string | null;
  cpu_model: string | null;
  logical_cpus: number | null;
  sockets: number | null;
  cores_per_socket: number | null;
  threads_per_core: number | null;
  numa_nodes: number | null;
  memory_bytes: number | null;
};

export type HostNetworkAdapterSummary = {
  name: string;
  mac: string | null;
  kind: string;
  state: string;
  management: boolean;
};

export type HostMetricSummary = {
  sampled_at: string;
  load_1: number;
  load_5: number;
  load_15: number;
  memory_total_kib: number;
  memory_available_kib: number;
  uptime_seconds: number;
};

export type HostDetail = {
  host: HostSummary;
  ssh_username: string;
  libvirt_uri: string;
  resource_counts: Record<string, number>;
  virtual_machines: VmSummary[];
  features: HostFeatureSummary[];
  hardware: HostHardwareSummary;
  network_adapters: HostNetworkAdapterSummary[];
  latest_metrics: HostMetricSummary | null;
  manage_url: string;
};

export type VmDiskSummary = {
  type: string | null;
  device: string | null;
  source: string | null;
  target: string | null;
  bus: string | null;
  format: string | null;
  readonly: boolean;
  shareable: boolean;
};

export type VmInterfaceSummary = {
  type: string | null;
  source: string | null;
  mac: string | null;
  target: string | null;
  model: string | null;
};

export type VmHostDeviceSummary = {
  type: string;
  address: string;
  category: string;
  name: string;
  driver: string | null;
  iommu_group: string | null;
};

export type VmSnapshotSummary = {
  resource_id: string;
  name: string;
  status: string;
  state: string;
  creation_time: string | null;
  current: boolean;
  memory: string | null;
  disks: string[];
  xml: string | null;
};

export type VmMetricSummary = {
  sampled_at: string;
  state: string;
  cpu_usage_percent: number | null;
  memory_usage_kib: number | null;
  disk_read_bytes: number | null;
  disk_write_bytes: number | null;
  net_rx_bytes: number | null;
  net_tx_bytes: number | null;
};

export type VmDetail = {
  vm: VmSummary;
  active: boolean;
  persistent: boolean;
  autostart: boolean;
  maximum_vcpus: number | null;
  configuration_status: string;
  disks: VmDiskSummary[];
  interfaces: VmInterfaceSummary[];
  host_devices: VmHostDeviceSummary[];
  snapshots: VmSnapshotSummary[];
  metrics: VmMetricSummary[];
  xml: string;
  manage_url: string;
};

export type VmLifecycleAction =
  | "start"
  | "shutdown"
  | "force_off"
  | "reboot"
  | "force_reboot"
  | "pause"
  | "resume"
  | "managed_save"
  | "autostart_enable"
  | "autostart_disable";

export type TaskSummary = {
  id: string;
  title: string;
  task_type: string;
  status: string;
  progress: number;
  current_step: number;
  total_steps: number;
  message: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  resumable: boolean;
  retry_count: number;
  max_retries: number;
  host_id: string | null;
  host_name: string | null;
};

export type TaskStepSummary = {
  sequence: number;
  name: string;
  status: string;
  attempt_count: number;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
};

export type TaskDetail = { task: TaskSummary; steps: TaskStepSummary[] };

export type MediaItemSummary = {
  id: string;
  relative_path: string;
  file_name: string;
  kind: string;
  status: string;
  size_bytes: number;
  sha256: string;
  image_format: string | null;
  classification: string | null;
  architecture: string | null;
  standalone: boolean;
};

export type GuestAgentSummary = {
  state: string;
  channel_configured: boolean;
  hostname: string | null;
  addresses: Array<{
    interface: string;
    address: string;
    prefix: number;
    family: string;
    mac: string | null;
  }>;
  message: string | null;
};

export type VmCreateVolumeOption = {
  id: string;
  host_id: string;
  host_name: string;
  pool_name: string;
  name: string;
  format: string;
  capacity_bytes: number;
};

export type VmCreateNetworkOption = {
  id: string;
  host_id: string;
  host_name: string;
  kind: string;
  name: string;
};

export type VmCreateIsoOption = {
  id: string;
  host_id: string;
  host_name: string;
  pool_name: string;
  name: string;
};

export type VmCreateOptions = {
  volumes: VmCreateVolumeOption[];
  networks: VmCreateNetworkOption[];
  isos: VmCreateIsoOption[];
};

export type VmCreatePreviewRequest = {
  name: string;
  memory_mib: number;
  vcpus: number;
  volume_resource_id: string;
  network_resource_id: string;
  iso_resource_id: string;
  driver_iso_resource_id: string;
  disk_bus: string;
  cpu_mode: string;
  guest_profile: string;
  firmware: string;
  secure_boot: boolean;
  tpm2: boolean;
};

export type VmCreatePreview = {
  plan_id: string;
  confirmation_token: string;
  host_id: string;
  vm_uuid: string;
  diff_text: string;
  summary: {
    name: string;
    host_name: string;
    vcpus: number;
    memory_mib: number;
    volume_name: string;
    network: string;
    iso_name: string | null;
    firmware: string;
    secure_boot: boolean;
    tpm2: boolean;
  };
};

export type VmBlankCreatePoolOption = {
  id: string;
  host_id: string;
  host_name: string;
  pool_name: string;
  target_path: string;
};

export type VmBlankCreateOptions = {
  pools: VmBlankCreatePoolOption[];
  networks: VmCreateNetworkOption[];
  isos: VmCreateIsoOption[];
};

export type VmBlankCreatePreviewRequest = {
  name: string;
  memory_mib: number;
  vcpus: number;
  pool_resource_id: string;
  disk_name: string;
  volume_format: string;
  capacity_gib: number;
  network_resource_id: string;
  iso_resource_id: string;
  driver_iso_resource_id: string;
  disk_bus: string;
  cpu_mode: string;
  guest_profile: string;
  firmware: string;
  secure_boot: boolean;
  tpm2: boolean;
};

export type VmBlankCreatePreview = {
  plan_id: string;
  confirmation_token: string;
  host_id: string;
  vm_uuid: string;
  diff_text: string;
  summary: {
    name: string;
    host_name: string;
    vcpus: number;
    memory_mib: number;
    pool_name: string;
    disk_name: string;
    volume_format: string;
    capacity_bytes: number;
    network: string;
    iso_name: string | null;
    firmware: string;
    secure_boot: boolean;
    tpm2: boolean;
  };
};

export type VmRemovePreview = {
  plan_id: string;
  confirmation_token: string;
  operation: string;
  target_name: string | null;
  remove_disks: boolean;
  remove_nvram: boolean;
  diff_text: string;
};

export type TaskCreated = { task_id: string; location: string };

export type HostOnboardingRequest = {
  name: string;
  address: string;
  ssh_port: number;
  ssh_username: string;
  authentication_method: string;
  password: string | null;
  private_key: string | null;
  private_key_passphrase: string | null;
  sudo_mode: string;
  labels: string[];
  notes: string | null;
};

export type HostOnboardingStarted = { host_id: string; location: string };

export type HostKeyConfirmation = {
  host_id: string;
  name: string;
  endpoint: string;
  host_key_digest: string;
  fingerprints: Array<{ key_type: string; fingerprint: string }>;
};

export type VmMediaCreateOptions = {
  media: Array<{ id: string; file_name: string; format: string; size_bytes: number; virtual_size_bytes: number | null }>;
  targets: Array<{ id: string; host_id: string; host_name: string; pool_name: string; target_path: string }>;
  networks: VmCreateNetworkOption[];
  isos: VmCreateIsoOption[];
};

export type VmMediaCreatePreviewRequest = {
  name: string;
  memory_mib: number;
  vcpus: number;
  media_item_id: string;
  pool_resource_id: string;
  target_file_name: string;
  target_capacity_gib: number | null;
  network_resource_id: string;
  iso_resource_id: string;
  driver_iso_resource_id: string;
  disk_bus: string;
  cpu_mode: string;
  guest_profile: string;
  firmware: string;
  secure_boot: boolean;
  tpm2: boolean;
  cloud_init: boolean;
  cloud_hostname: string;
  cloud_username: string;
  cloud_ssh_public_key: string;
  cloud_password: string;
  cloud_password_confirmation: string;
  cloud_network_mode: string;
  cloud_ipv4_cidr: string;
  cloud_ipv4_gateway: string;
  cloud_ipv6_cidr: string;
  cloud_ipv6_gateway: string;
  cloud_dns_addresses: string[];
};

export type VmMediaCreatePreview = {
  plan_id: string;
  confirmation_token: string;
  host_id: string;
  vm_uuid: string;
  diff_text: string;
  summary: {
    name: string;
    host_name: string;
    media_name: string;
    pool_name: string;
    target_path: string;
    source_sha256: string;
    vcpus: number;
    memory_mib: number;
    target_capacity_bytes: number | null;
    network: string;
    iso_name: string | null;
    driver_iso_name: string | null;
    firmware: string;
    secure_boot: boolean;
    tpm2: boolean;
    cloud_init: string | null;
  };
};

export type StorageOverview = {
  hosts: Array<{ id: string; name: string }>;
  pools: StoragePoolSummary[];
  volumes: StorageVolumeSummary[];
};

export type StoragePoolSummary = {
  resource_id: string;
  host_id: string;
  host_name: string;
  native_id: string;
  name: string;
  status: string;
  pool_type: string;
  state: string;
  active: boolean;
  autostart: boolean;
  target_path: string | null;
  capacity_bytes: number | null;
  available_bytes: number | null;
  writable: boolean;
};

export type StorageVolumeSummary = {
  resource_id: string;
  host_id: string;
  host_name: string;
  pool_resource_id: string;
  pool_name: string;
  name: string;
  status: string;
  format: string | null;
  capacity_bytes: number | null;
  allocation_bytes: number | null;
  in_use: boolean;
  writable: boolean;
};

export type StorageChangePreview = {
  plan_id: string;
  confirmation_token: string;
  host_id: string;
  pool_uuid: string;
  diff_text: string;
  operation: string;
  summary: Record<string, unknown>;
};

export type StoragePoolCreateRequest = {
  host_id: string;
  name: string;
  pool_type: string;
  target_path: string;
  source_host: string | null;
  source_path: string | null;
  nfs_version: string | null;
  mount_options: string[];
  start: boolean;
  autostart: boolean;
};

export type StorageVolumeCreateRequest = {
  pool_resource_id: string;
  name: string;
  volume_format: string;
  capacity_gib: number;
};
