"""Validated and recoverable Nexora archive restoration."""

import hmac
import json
import tarfile
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from nexora.operations.constants import BACKUP_FORMAT, PERSISTENT_DIRECTORIES
from nexora.operations.database import verify_database

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1_000_000


def restore_backup(data_dir: Path, archive_path: Path, *, replace: bool = False) -> Path:
    """Restore validated data and retain replaced content as a recovery point."""

    live_database = data_dir / "database" / "nexora.sqlite3"
    if live_database.exists() and not replace:
        raise FileExistsError("live database exists; explicit replace is required")
    recovery_root = data_dir / "recovery"
    recovery_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=recovery_root) as temporary:
        staging = Path(temporary)
        with tarfile.open(archive_path, mode="r:*") as archive:
            _validate_members(archive)
            archive.extractall(staging, filter="data")
        manifest = _load_manifest(staging / "manifest.json")
        database = staging / "database" / "nexora.sqlite3"
        verify_database(database)
        expected_digest = str(manifest["database_sha256"])
        if not hmac.compare_digest(expected_digest, _file_digest(database)):
            raise ValueError("backup database checksum does not match manifest")
        return _install_staging(data_dir, staging, replace=replace)


def _validate_members(archive: tarfile.TarFile) -> None:
    members = archive.getmembers()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("backup archive contains too many members")
    if sum(member.size for member in members) > MAX_ARCHIVE_BYTES:
        raise ValueError("backup archive is too large")
    seen: set[str] = set()
    allowed_roots = set(PERSISTENT_DIRECTORIES) | {"manifest.json"}
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("backup archive contains an unsafe path")
        normalized_name = path.as_posix()
        if normalized_name != member.name.rstrip("/"):
            raise ValueError("backup archive contains a non-canonical path")
        if path.parts[0] not in allowed_roots:
            raise ValueError("backup archive contains an unexpected path")
        if normalized_name in seen:
            raise ValueError("backup archive contains duplicate paths")
        if member.issym() or member.islnk() or member.isdev():
            raise ValueError("backup archive contains an unsafe member type")
        seen.add(normalized_name)


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > 64 * 1024:
        raise ValueError("backup manifest is missing or too large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format") != BACKUP_FORMAT:
        raise ValueError("unsupported backup format")
    if not isinstance(value.get("database_sha256"), str):
        raise ValueError("backup manifest has no database checksum")
    return value


def _install_staging(data_dir: Path, staging: Path, *, replace: bool) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stamp = f"{stamp}-{uuid4().hex[:8]}"
    recovery_point = data_dir / "recovery" / f"pre-restore-{stamp}"
    recovery_point.mkdir(mode=0o700)
    installed: list[str] = []
    try:
        for name in PERSISTENT_DIRECTORIES:
            source = staging / name
            destination = data_dir / name
            previous = recovery_point / name
            installed.append(name)
            if destination.exists():
                if not replace:
                    raise FileExistsError(f"persistent directory exists: {name}")
                destination.replace(previous)
            if source.exists():
                source.replace(destination)
            else:
                destination.mkdir(mode=0o700)
    except Exception:
        _rollback_install(data_dir, staging, recovery_point, installed)
        raise
    return recovery_point


def _rollback_install(
    data_dir: Path,
    staging: Path,
    recovery_point: Path,
    installed: list[str],
) -> None:
    for name in reversed(installed):
        destination = data_dir / name
        if destination.exists():
            destination.replace(staging / name)
        previous = recovery_point / name
        if previous.exists():
            previous.replace(destination)


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
