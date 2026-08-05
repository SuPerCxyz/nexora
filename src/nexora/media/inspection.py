"""Bounded qemu-img metadata inspection for platform images."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MAX_INSPECT_OUTPUT = 1024 * 1024


@dataclass(frozen=True)
class ImageInfo:
    image_format: str
    virtual_size_bytes: int
    backing_files: tuple[str, ...]


class ImageInspector(Protocol):
    def inspect(self, path: Path) -> ImageInfo: ...


class QemuImageInspector:
    def inspect(self, path: Path) -> ImageInfo:
        try:
            process = subprocess.run(
                [
                    "qemu-img",
                    "info",
                    "--output=json",
                    "--backing-chain",
                    str(path),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("qemu-img inspection failed") from exc
        if process.returncode != 0:
            raise ValueError("qemu-img rejected media image")
        if len(process.stdout) > MAX_INSPECT_OUTPUT:
            raise ValueError("qemu-img output exceeds safety limit")
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("qemu-img returned invalid JSON") from exc
        entries = payload if isinstance(payload, list) else [payload]
        if not entries or not all(isinstance(entry, dict) for entry in entries):
            raise ValueError("qemu-img returned invalid image metadata")
        first = entries[0]
        image_format = first.get("format")
        virtual_size = first.get("virtual-size")
        if not isinstance(image_format, str) or not isinstance(virtual_size, int):
            raise ValueError("qemu-img omitted required image metadata")
        backing_files = tuple(
            value for entry in entries[1:] if isinstance((value := entry.get("filename")), str)
        )
        return ImageInfo(image_format[:32], virtual_size, backing_files)
