from datetime import UTC, datetime
from hashlib import sha256

import pytest

from media.copy_support import Executor, Transfer
from nexora.media.copy_errors import MediaCopyError
from nexora.media.iso_cache import MediaIsoCache
from nexora.media.models import MediaItem, MediaStatus


def test_iso_cache_copies_verifies_reuses_and_removes(settings) -> None:
    content = b"small-platform-iso"
    source = settings.library_dir / "iso" / "linux" / "test.iso"
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    metadata = source.stat()
    item = MediaItem(
        id="11111111-1111-1111-1111-111111111111",
        relative_path="iso/linux/test.iso",
        file_name="test.iso",
        kind="iso",
        status=MediaStatus.AVAILABLE,
        size_bytes=len(content),
        modified_ns=metadata.st_mtime_ns,
        file_device=metadata.st_dev,
        file_inode=metadata.st_ino,
        sha256=sha256(content).hexdigest(),
        image_format=None,
        backing_chain_json="[]",
        observed_generation=1,
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    remote_files: dict[str, bytes] = {}
    executor = Executor(remote_files)
    transfer = Transfer(remote_files)
    cache = MediaIsoCache(settings.library_dir, executor, transfer)  # type: ignore[arg-type]

    first = cache.ensure("host-1", item, task_id="task-1", sudo=False)
    second = cache.ensure("host-1", item, task_id="task-2", sudo=False)

    assert first.created is True
    assert second.created is False
    assert first.path == f"/var/tmp/nexora-media-{item.sha256}.iso"
    assert remote_files[first.path] == content
    assert transfer.calls == 1
    cache.remove("host-1", first.path, sudo=False)
    assert first.path not in remote_files


def test_iso_cache_rejects_paths_outside_managed_namespace(settings) -> None:
    cache = MediaIsoCache(settings.library_dir, Executor({}), Transfer({}))  # type: ignore[arg-type]

    with pytest.raises(MediaCopyError, match="managed namespace"):
        cache.remove("host-1", "/var/tmp/business.iso", sudo=False)
