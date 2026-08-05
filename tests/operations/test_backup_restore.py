import sqlite3
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.operations.backup import create_backup
from nexora.operations.restore import restore_backup


def _prepare_database(settings: Settings, value: str) -> None:
    database = Database(settings)
    try:
        upgrade_database(database)
    finally:
        database.dispose()
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("CREATE TABLE backup_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO backup_marker VALUES (?)", (value,))


def _marker(database_path: Path) -> str:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT value FROM backup_marker").fetchone()
        assert row is not None
        return str(row[0])


def test_backup_and_restore_preserve_data_with_recovery_point(
    settings: Settings,
    tmp_path: Path,
) -> None:
    _prepare_database(settings, "before")
    credentials = settings.data_dir / "credentials"
    credentials.mkdir(mode=0o700)
    (credentials / "host.enc").write_bytes(b"ciphertext")
    archive = create_backup(settings.data_dir, tmp_path / "backup.tar.gz")
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("UPDATE backup_marker SET value = ?", ("after",))

    recovery = restore_backup(settings.data_dir, archive, replace=True)

    assert "before" == _marker(settings.database_path)
    assert b"ciphertext" == (credentials / "host.enc").read_bytes()
    assert "after" == _marker(recovery / "database" / "nexora.sqlite3")
    assert 0o600 == archive.stat().st_mode & 0o777


def test_restore_refuses_to_replace_live_data_without_explicit_flag(
    settings: Settings,
    tmp_path: Path,
) -> None:
    _prepare_database(settings, "before")
    archive = create_backup(settings.data_dir, tmp_path / "backup.tar.gz")

    with pytest.raises(FileExistsError, match="explicit replace"):
        restore_backup(settings.data_dir, archive)


def test_backup_rejects_symlinks(settings: Settings, tmp_path: Path) -> None:
    _prepare_database(settings, "before")
    credentials = settings.data_dir / "credentials"
    credentials.mkdir(mode=0o700)
    (credentials / "escape").symlink_to(tmp_path / "outside")

    with pytest.raises(ValueError, match="symlink"):
        create_backup(settings.data_dir, tmp_path / "backup.tar.gz")


def test_backup_output_cannot_be_inside_archived_data(settings: Settings) -> None:
    _prepare_database(settings, "before")

    with pytest.raises(ValueError, match="inside archived data"):
        create_backup(
            settings.data_dir,
            settings.data_dir / "credentials" / "backup.tar.gz",
        )


def test_restore_rejects_archive_path_traversal(settings: Settings, tmp_path: Path) -> None:
    archive_path = tmp_path / "malicious.tar.gz"
    payload = b"escape"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("../escape")
        member.size = len(payload)
        archive.addfile(member, BytesIO(payload))

    with pytest.raises(ValueError, match="unsafe path"):
        restore_backup(settings.data_dir, archive_path)

    assert (tmp_path / "escape").exists() is False
