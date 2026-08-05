import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexora.media.models import MediaItem, MediaStatus
from nexora.media.ranges import MediaRangeError, open_indexed_media, parse_range


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("bytes=0-3", (0, 3)),
        ("bytes=4-", (4, 9)),
        ("bytes=-4", (6, 9)),
        ("bytes=0-99", (0, 9)),
    ],
)
def test_parse_single_range(value: str, expected: tuple[int, int]) -> None:
    selected = parse_range(value, 10)
    assert expected == (selected.start, selected.end)


@pytest.mark.parametrize(
    "value",
    ["items=0-1", "bytes=10-11", "bytes=4-3", "bytes=0-1,3-4", "bytes=-0"],
)
def test_reject_invalid_or_multipart_range(value: str) -> None:
    with pytest.raises(MediaRangeError):
        parse_range(value, 10)


def test_open_indexed_media_rejects_replaced_file(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    path = library / "test.iso"
    path.write_bytes(b"first")
    metadata = path.stat()
    item = _item(metadata)
    replacement = library / "replacement"
    replacement.write_bytes(b"other")
    os.utime(replacement, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    replacement.replace(path)

    with pytest.raises(OSError, match="version changed"):
        open_indexed_media(library, item)


def _item(metadata: os.stat_result) -> MediaItem:
    now = datetime.now(UTC)
    return MediaItem(
        id="media-1",
        relative_path="test.iso",
        file_name="test.iso",
        kind="iso",
        status=MediaStatus.AVAILABLE,
        size_bytes=metadata.st_size,
        modified_ns=metadata.st_mtime_ns,
        file_device=metadata.st_dev,
        file_inode=metadata.st_ino,
        sha256="a" * 64,
        backing_chain_json="[]",
        observed_generation=1,
        first_seen_at=now,
        last_seen_at=now,
    )
