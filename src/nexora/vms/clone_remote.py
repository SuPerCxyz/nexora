"""Fixed remote operations used by full VM cloning."""

import json
from dataclasses import dataclass

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.vms.creation_remote import VmCreationRemote


@dataclass(frozen=True)
class RemoteFileInfo:
    size_bytes: int
    format: str | None


class VmCloneRemote:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.database = database
        self.executor = executor
        self.creation = VmCreationRemote(database, executor)

    def inspect_source(self, host_id: str, path: str, *, disk: bool) -> RemoteFileInfo:
        stat = self._run(host_id, CommandSpec("stat", ("--format=%F|%s", "--", path)), 30)
        _require(stat, "clone source file is unavailable")
        try:
            kind, size = stat.stdout.decode().strip().split("|", 1)
            size_bytes = int(size)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("clone source metadata is invalid") from exc
        if kind != "regular file" or size_bytes < 0:
            raise ValueError("clone source must be a regular file")
        if not disk:
            return RemoteFileInfo(size_bytes, None)
        info = self._run(
            host_id,
            CommandSpec("qemu-img", ("info", "-U", "--output=json", "--", path)),
            60,
        )
        _require(info, "cannot inspect clone source image")
        payload = json.loads(info.stdout)
        image_format = payload.get("format")
        if image_format not in {"qcow2", "raw"}:
            raise ValueError("clone source image format is unsupported")
        if payload.get("backing-filename") or payload.get("full-backing-filename"):
            raise ValueError("clone source image has an external backing chain")
        return RemoteFileInfo(size_bytes, str(image_format))

    def target_available(self, host_id: str, final_path: str, partial_path: str) -> None:
        for path in (final_path, partial_path):
            result = self._run(host_id, CommandSpec("test", ("!", "-e", path)), 30)
            _require(result, "clone target or partial file already exists")

    def exists(self, host_id: str, path: str) -> bool:
        result = self._run(host_id, CommandSpec("test", ("-e", path)), 30)
        if result.timed_out or result.cancelled:
            raise ValueError("clone target existence check failed")
        return result.exit_code == 0

    def sha256(self, host_id: str, path: str) -> str:
        result = self._run(host_id, CommandSpec("sha256sum", ("--", path)), 86_400)
        _require(result, "clone file SHA-256 failed")
        value = result.stdout.decode().split(maxsplit=1)[0]
        if len(value) != 64:
            raise ValueError("clone file SHA-256 is invalid")
        return value

    def publish(self, host_id: str, partial_path: str, final_path: str) -> None:
        _require(
            self._run(host_id, CommandSpec("ln", ("--", partial_path, final_path)), 30),
            "clone file no-overwrite publish failed",
        )
        _require(
            self._run(host_id, CommandSpec("rm", ("--", partial_path)), 30),
            "clone partial cleanup failed after publish",
        )

    def cleanup_partial(self, host_id: str, partial_path: str) -> None:
        self._run(host_id, CommandSpec("rm", ("-f", "--", partial_path)), 30)

    def validate_xml(self, host_id: str, content: bytes) -> None:
        self.creation.validate_xml(host_id, content)

    def define(self, host_id: str, content: bytes) -> None:
        self.creation.define(host_id, content)

    def architecture(self, host_id: str) -> str:
        return self.creation.architecture(host_id)

    def _run(self, host_id: str, command: CommandSpec, timeout: int) -> CommandResult:
        host = self._host(host_id)
        return self.executor.run(
            host_id,
            command,
            sudo=host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS,
            timeout=timeout,
            env={"LC_ALL": "C"},
        )

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise ValueError("clone host not found")
            return host


def _require(result: CommandResult, message: str) -> None:
    if result.exit_code or result.timed_out or result.cancelled:
        raise ValueError(message)
