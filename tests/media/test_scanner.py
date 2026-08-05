from hashlib import sha256
from pathlib import Path

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.media.inspection import ImageInfo
from nexora.media.models import MediaStatus
from nexora.media.scanner import MediaScanner
from nexora.media.store import MediaIndexStore


class Inspector:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def inspect(self, path: Path) -> ImageInfo:
        if self.fail:
            raise ValueError("inspection failure")
        kind = path.suffix.removeprefix(".")
        backing = ("../../../../outside/base.qcow2",) if kind == "qcow2" else ()
        return ImageInfo(kind, path.stat().st_size * 2, backing)


def test_scan_indexes_supported_files_without_following_symlink(
    settings: Settings,
    tmp_path: Path,
) -> None:
    library = settings.library_dir
    (library / "iso" / "windows").mkdir(parents=True)
    (library / "images" / "cloud").mkdir(parents=True)
    iso = library / "iso" / "windows" / "server-amd64.iso"
    qcow = library / "images" / "cloud" / "ubuntu-aarch64.qcow2"
    iso.write_bytes(b"iso-content")
    qcow.write_bytes(b"qcow-content")
    outside = tmp_path / "outside.raw"
    outside.write_bytes(b"must-not-index")
    (library / "escape.raw").symlink_to(outside)
    database = _database(settings)
    store = MediaIndexStore(database)

    result = MediaScanner(library, store, Inspector()).scan()
    items = store.list_items()

    assert "files=2" in result
    assert {
        "iso/windows/server-amd64.iso",
        "images/cloud/ubuntu-aarch64.qcow2",
    } == {item.relative_path for item in items}
    indexed_iso = next(item for item in items if item.kind == "iso")
    indexed_qcow = next(item for item in items if item.kind == "qcow2")
    assert sha256(b"iso-content").hexdigest() == indexed_iso.sha256
    assert "windows_iso" == indexed_iso.classification
    assert "x86_64" == indexed_iso.architecture
    assert "cloud_image" == indexed_qcow.classification
    assert "aarch64" == indexed_qcow.architecture
    assert '["[external]"]' == indexed_qcow.backing_chain_json
    database.dispose()


def test_successful_rescan_marks_missing_but_preserves_notes(settings: Settings) -> None:
    settings.library_dir.mkdir(parents=True)
    image = settings.library_dir / "base.raw"
    image.write_bytes(b"raw")
    database = _database(settings)
    store = MediaIndexStore(database)
    scanner = MediaScanner(settings.library_dir, store, Inspector())
    scanner.scan()
    with database.session() as session:
        item = store.list_items()[0]
        stored = session.get(type(item), item.id)
        assert stored is not None
        stored.notes = "keep this note"
    image.unlink()

    scanner.scan()

    item = store.list_items()[0]
    assert MediaStatus.MISSING == item.status
    assert "keep this note" == item.notes
    database.dispose()


def test_failed_scan_does_not_mark_previous_index_missing(settings: Settings) -> None:
    settings.library_dir.mkdir(parents=True)
    image = settings.library_dir / "base.raw"
    image.write_bytes(b"raw")
    database = _database(settings)
    store = MediaIndexStore(database)
    MediaScanner(settings.library_dir, store, Inspector()).scan()

    with pytest.raises(ValueError, match="inspection failure"):
        MediaScanner(settings.library_dir, store, Inspector(fail=True)).scan()

    item = store.list_items()[0]
    assert MediaStatus.AVAILABLE == item.status
    database.dispose()


def _database(settings: Settings) -> Database:
    database = Database(settings)
    upgrade_database(database)
    return database
