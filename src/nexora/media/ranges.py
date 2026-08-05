"""HTTP single-range parsing and safely opened indexed media files."""

import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from nexora.media.models import MediaItem

STREAM_CHUNK_SIZE = 1024 * 1024


class MediaRangeError(ValueError):
    pass


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass
class OpenedMedia:
    descriptor: int
    size_bytes: int

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def chunks(self, selected: ByteRange) -> Iterator[bytes]:
        try:
            os.lseek(self.descriptor, selected.start, os.SEEK_SET)
            remaining = selected.length
            while remaining:
                chunk = os.read(self.descriptor, min(STREAM_CHUNK_SIZE, remaining))
                if not chunk:
                    raise OSError("media file ended before indexed size")
                remaining -= len(chunk)
                yield chunk
        finally:
            self.close()


def parse_range(value: str, size: int) -> ByteRange:
    if size < 1 or not value.startswith("bytes=") or "," in value:
        raise MediaRangeError("unsupported byte range")
    specification = value.removeprefix("bytes=")
    if "-" not in specification:
        raise MediaRangeError("invalid byte range")
    start_text, end_text = specification.split("-", 1)
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix < 1:
                raise MediaRangeError("invalid byte range")
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(start_text)
            end = size - 1 if not end_text else int(end_text)
    except ValueError as exc:
        raise MediaRangeError("invalid byte range") from exc
    if start < 0 or start >= size or end < start:
        raise MediaRangeError("unsatisfiable byte range")
    return ByteRange(start, min(end, size - 1))


def open_indexed_media(library_dir: Path, item: MediaItem) -> OpenedMedia:
    relative = PurePosixPath(item.relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise OSError("indexed media path is unsafe")
    root = library_dir.resolve(strict=True)
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root):
        raise OSError("indexed media escaped library root")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        actual = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
        expected = (
            item.file_device,
            item.file_inode,
            item.size_bytes,
            item.modified_ns,
        )
        if actual != expected or not stat.S_ISREG(metadata.st_mode):
            raise OSError("indexed media file version changed")
        return OpenedMedia(descriptor, metadata.st_size)
    except Exception:
        os.close(descriptor)
        raise
