"""Safe Nexora data archive creation."""

import json
import os
import tarfile
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from nexora import __version__
from nexora.operations.constants import BACKUP_FORMAT, PERSISTENT_DIRECTORIES
from nexora.operations.database import migration_revision, online_backup, verify_database


def create_backup(data_dir: Path, output: Path) -> Path:
    """Create one atomic archive with a transactionally consistent SQLite copy."""

    source_database = data_dir / "database" / "nexora.sqlite3"
    if not source_database.is_file():
        raise FileNotFoundError("Nexora database does not exist")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in PERSISTENT_DIRECTORIES:
        if output.is_relative_to((data_dir / directory).resolve()):
            raise ValueError("backup output cannot be inside archived data")
    partial = output.with_name(f"{output.name}.partial")
    if output.exists() or partial.exists():
        raise FileExistsError("backup destination already exists")
    try:
        with tempfile.TemporaryDirectory(prefix="nexora-backup-") as temporary:
            snapshot = Path(temporary) / "nexora.sqlite3"
            online_backup(source_database, snapshot)
            verify_database(snapshot)
            manifest = _manifest(snapshot)
            with tarfile.open(partial, mode="x:gz", dereference=False) as archive:
                _add_bytes(archive, "manifest.json", json.dumps(manifest, indent=2).encode())
                archive.add(snapshot, arcname="database/nexora.sqlite3", recursive=False)
                for directory in PERSISTENT_DIRECTORIES:
                    if directory != "database":
                        _add_tree(archive, data_dir / directory, Path(directory))
        os.chmod(partial, 0o600)
        partial.replace(output)
        return output
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _manifest(snapshot: Path) -> dict[str, object]:
    return {
        "format": BACKUP_FORMAT,
        "created_at": datetime.now(UTC).isoformat(),
        "nexora_version": __version__,
        "alembic_revision": migration_revision(snapshot),
        "database_sha256": _file_digest(snapshot),
        "directories": list(PERSISTENT_DIRECTORIES),
    }


def _add_tree(archive: tarfile.TarFile, source: Path, archive_path: Path) -> None:
    if not source.exists():
        return
    if source.is_symlink():
        raise ValueError(f"backup source contains a symlink: {source}")
    archive.add(source, arcname=archive_path.as_posix(), recursive=False)
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        child_archive_path = archive_path / child.name
        if child.is_symlink():
            raise ValueError(f"backup source contains a symlink: {child}")
        if child.is_dir():
            _add_tree(archive, child, child_archive_path)
        elif child.is_file():
            archive.add(child, arcname=child_archive_path.as_posix(), recursive=False)
        else:
            raise ValueError(f"backup source is not a regular file: {child}")


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o600
    info.mtime = int(datetime.now(UTC).timestamp())
    archive.addfile(info, BytesIO(payload))


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
