"""Internal React contracts for storage management."""

from pydantic import BaseModel, Field


class StorageHostOption(BaseModel):
    id: str
    name: str


class StoragePoolSummary(BaseModel):
    resource_id: str
    host_id: str
    host_name: str
    native_id: str
    name: str
    status: str
    pool_type: str
    state: str
    active: bool
    autostart: bool
    target_path: str | None
    capacity_bytes: int | None
    available_bytes: int | None
    writable: bool


class StorageVolumeSummary(BaseModel):
    resource_id: str
    host_id: str
    host_name: str
    pool_resource_id: str
    pool_name: str
    name: str
    status: str
    format: str | None
    capacity_bytes: int | None
    allocation_bytes: int | None
    in_use: bool
    writable: bool


class StorageOverviewResponse(BaseModel):
    hosts: list[StorageHostOption]
    pools: list[StoragePoolSummary]
    volumes: list[StorageVolumeSummary]


class StoragePoolCreateRequest(BaseModel):
    host_id: str
    name: str = Field(min_length=1, max_length=128)
    pool_type: str
    target_path: str = Field(min_length=1, max_length=1_024)
    source_host: str | None = None
    source_path: str | None = None
    nfs_version: str | None = None
    mount_options: list[str] = Field(default_factory=list, max_length=16)
    start: bool = True
    autostart: bool = True


class StoragePoolPreviewSummary(BaseModel):
    name: str
    pool_type: str
    target_path: str
    pool_uuid: str
    start: bool
    autostart: bool


class StorageChangePreviewResponse(BaseModel):
    plan_id: str
    confirmation_token: str
    host_id: str
    pool_uuid: str
    diff_text: str
    operation: str
    summary: dict[str, object]


class StorageChangeApplyRequest(BaseModel):
    plan_id: str
    confirmation_token: str
    host_id: str
    pool_uuid: str


class StorageVolumeCreateRequest(BaseModel):
    pool_resource_id: str
    name: str = Field(min_length=1, max_length=255)
    volume_format: str
    capacity_gib: int = Field(ge=1, le=8 * 1024**2)


class StorageVolumePreviewSummary(BaseModel):
    name: str
    pool_name: str
    volume_format: str
    capacity_bytes: int


class StoragePoolLifecycleRequest(BaseModel):
    resource_id: str
    action: str
