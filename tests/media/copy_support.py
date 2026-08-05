import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.media.copy import MediaImageCopyService
from nexora.media.copy_authority import MediaCopyAuthority
from nexora.media.copy_contracts import MediaCopyInput
from nexora.media.models import MediaItem, MediaStatus
from nexora.remote.executor import CommandResult
from nexora.remote.transfer import TransferResult
from nexora.resources.conflicts import ResourceWriteGuard
from nexora.resources.contracts import ResourceObservation
from nexora.resources.index_store import ResourceIndexStore
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.tasks.locks import ResourceLockStore

MEDIA_ID = "11111111-1111-1111-1111-111111111111"
POOL_ID = "22222222-2222-2222-2222-222222222222"
POOL_NATIVE_ID = "33333333-3333-3333-3333-333333333333"


class Executor:
    def __init__(self, remote_files: dict[str, bytes]) -> None:
        self.remote_files = remote_files
        self.commands: list[tuple[str, ...]] = []

    def run(self, _host_id: str, command, **_kwargs: object) -> CommandResult:
        argv = command.argv()
        self.commands.append(argv)
        exit_code = 0
        stdout = b""
        if argv[0] == "test" and argv[1] == "-e":
            exit_code = 0 if argv[2] in self.remote_files else 1
        elif argv[0] == "df":
            stdout = (
                b"Filesystem 1B-blocks Used Available Capacity Mounted on\n"
                b"x 1 0 999999999 0% /pool\n"
            )
        elif argv[0] == "stat":
            stdout = str(len(self.remote_files[argv[-1]])).encode() + b"\n"
        elif argv[0] == "sha256sum":
            stdout = sha256(self.remote_files[argv[-1]]).hexdigest().encode() + b"  file\n"
        elif argv[0] == "ln":
            source, target = argv[-2:]
            if target in self.remote_files:
                exit_code = 1
            else:
                self.remote_files[target] = self.remote_files[source]
        elif argv[0] == "rm":
            self.remote_files.pop(argv[-1], None)
        return CommandResult(
            "operation",
            exit_code,
            stdout,
            b"",
            False,
            False,
            False,
            False,
            0.01,
        )


class Transfer:
    def __init__(self, remote_files: dict[str, bytes], *, corrupt: bool = False) -> None:
        self.remote_files = remote_files
        self.corrupt = corrupt
        self.calls = 0

    def upload(self, _host_id: str, descriptor: int, command, **_kwargs: object) -> TransferResult:
        self.calls += 1
        target = next(
            value.removeprefix("of=") for value in command.argv() if value.startswith("of=")
        )
        os.lseek(descriptor, 0, os.SEEK_SET)
        content = bytearray()
        while chunk := os.read(descriptor, 1024):
            content.extend(chunk)
        self.remote_files[target] = b"x" * len(content) if self.corrupt else bytes(content)
        return TransferResult(
            "transfer",
            0,
            len(content),
            b"",
            False,
            False,
            0.01,
        )


class PoolDiscovery:
    def __init__(self, persistent_hash: str = "b" * 64) -> None:
        self.persistent_hash = persistent_hash

    def read_pool(self, _host_id: str, pool_uuid: str) -> ResourceObservation:
        return ResourceObservation(
            native_id=pool_uuid,
            display_name="default",
            status=ResourceStatus.MANAGED,
            persistent_hash=self.persistent_hash,
            live_hash=None,
            details={"pool_type": "dir", "active": True, "target_path": "/pool"},
        )


def runtime(settings: Settings) -> tuple[Database, MediaCopyInput, bytes]:
    settings.library_dir.mkdir(parents=True)
    source_path = settings.library_dir / "images" / "base.raw"
    source_path.parent.mkdir()
    source = b"platform-image-content"
    source_path.write_bytes(source)
    metadata = source_path.stat()
    database = Database(settings)
    upgrade_database(database)
    now = datetime.now(UTC)
    media_hash = sha256(source).hexdigest()
    with database.session() as session:
        session.add(_host(now))
        session.add(
            MediaItem(
                id=MEDIA_ID,
                relative_path="images/base.raw",
                file_name="base.raw",
                kind="raw",
                status=MediaStatus.AVAILABLE,
                size_bytes=len(source),
                modified_ns=metadata.st_mtime_ns,
                file_device=metadata.st_dev,
                file_inode=metadata.st_ino,
                sha256=media_hash,
                image_format="raw",
                backing_chain_json="[]",
                observed_generation=1,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.add(_pool(now))
    return (
        database,
        MediaCopyInput(
            MEDIA_ID,
            media_hash,
            "host-1",
            POOL_ID,
            POOL_NATIVE_ID,
            1,
            "b" * 64,
            "base.raw",
        ),
        source,
    )


def service(
    database: Database,
    settings: Settings,
    executor: Executor,
    transfer: Transfer,
    *,
    authoritative_pool_hash: str = "b" * 64,
) -> MediaImageCopyService:
    store = ResourceIndexStore(database)
    return MediaImageCopyService(
        settings.library_dir,
        cast(Any, executor),
        cast(Any, transfer),
        MediaCopyAuthority(
            database,
            cast(Any, PoolDiscovery(authoritative_pool_hash)),
            store,
            ResourceWriteGuard(database),
            ResourceLockStore(database),
        ),
    )


def _host(now: datetime) -> Host:
    return Host(
        id="host-1",
        name="node",
        address="node.example.test",
        ssh_port=22,
        ssh_username="root",
        authentication_method=AuthenticationMethod.PRIVATE_KEY,
        sudo_mode=SudoMode.NONE,
        libvirt_uri="qemu:///system",
        status=HostStatus.READY,
        labels_json="[]",
        created_at=now,
        updated_at=now,
    )


def _pool(now: datetime) -> ResourceIndex:
    return ResourceIndex(
        id=POOL_ID,
        host_id="host-1",
        resource_type=ResourceType.STORAGE_POOL,
        native_id=POOL_NATIVE_ID,
        display_name="default",
        status=ResourceStatus.MANAGED,
        source="existing",
        persistent_hash="b" * 64,
        observed_generation=1,
        details_json=json.dumps({"pool_type": "dir", "active": True, "target_path": "/pool"}),
        labels_json="[]",
        first_seen_at=now,
        last_seen_at=now,
    )
