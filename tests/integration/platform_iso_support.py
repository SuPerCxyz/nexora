"""Local HTTP server and media fixtures for platform ISO integration."""

import hashlib
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import SplitResult

from fastapi.testclient import TestClient

from nexora.config import Settings
from nexora.media.models import MediaItem
from nexora.media.store import MediaObservation


def media_file(library_dir: Path) -> Path:
    path = library_dir / "iso" / "nexora-it-platform.iso"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\0" * 1024**2)
    return path


def index_media(client: TestClient, path: Path) -> MediaItem:
    stat = path.stat()
    store = client.app.state.media_index_store
    scan = store.begin()
    store.complete(
        scan.id,
        [
            MediaObservation(
                "iso/nexora-it-platform.iso",
                path.name,
                "iso",
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_dev,
                stat.st_ino,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                None,
                None,
                (),
                "linux_iso",
                "x86_64",
            )
        ],
    )
    return store.list_items()[0]


def start_media_server(
    settings: Settings,
    origin: SplitResult,
) -> subprocess.Popen[bytes]:
    assert settings.credential_key is not None
    environment = {
        **os.environ,
        "NEXORA_ENVIRONMENT": "test",
        "NEXORA_DATA_DIR": str(settings.data_dir),
        "NEXORA_LIBRARY_DIR": str(settings.library_dir),
        "NEXORA_CREDENTIAL_KEY": settings.credential_key.get_secret_value(),
        "NEXORA_SESSION_COOKIE_SECURE": "false",
        "NEXORA_TRUSTED_HOSTS": f"127.0.0.1,localhost,{origin.hostname}",
        "NEXORA_MEDIA_PUBLIC_BASE_URL": str(settings.media_public_base_url),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "nexora.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(origin.port),
            "--no-access-log",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    _wait_server(origin, process)
    return process


def _wait_server(
    origin: SplitResult,
    process: subprocess.Popen[bytes],
) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{origin.port}/ready",
        headers={"Host": str(origin.hostname)},
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
            raise AssertionError(f"media server exited: {stderr[-1000:]}")
        try:
            with urllib.request.urlopen(request, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("media server did not become ready")


def stop_server(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
