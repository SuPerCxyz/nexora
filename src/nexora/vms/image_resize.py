"""Recovery-aware remote grow-only image resizing."""

import json
from pathlib import PurePosixPath

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor


class ImageResizeError(RuntimeError):
    pass


class ImageResizeRemote:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.database = database
        self.executor = executor

    def virtual_size(self, host_id: str, path: str) -> int | None:
        _validate_path(path)
        existence = self._run(host_id, CommandSpec("test", ("-e", path)), 30)
        if existence.exit_code == 1 and not existence.timed_out:
            return None
        _require(existence, "target image existence check failed")
        result = self._run(
            host_id,
            CommandSpec("qemu-img", ("info", "--output=json", "--", path)),
            60,
        )
        _require(result, "target image inspection failed")
        try:
            value = json.loads(result.stdout)["virtual-size"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ImageResizeError("target image virtual size is invalid") from exc
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ImageResizeError("target image virtual size is invalid")
        return value

    def grow(self, host_id: str, path: str, expected: int, target: int) -> None:
        current = self.virtual_size(host_id, path)
        if current == target:
            return
        if current != expected or target < expected:
            raise ImageResizeError("target image capacity changed unexpectedly")
        result = self._run(
            host_id,
            CommandSpec("qemu-img", ("resize", "--", path, str(target))),
            300,
        )
        _require(result, "target image grow failed")
        if self.virtual_size(host_id, path) != target:
            raise ImageResizeError("target image grow verification failed")

    def sha256(self, host_id: str, path: str) -> str:
        result = self._run(host_id, CommandSpec("sha256sum", ("--", path)), 86_400)
        _require(result, "resized image SHA-256 failed")
        value = result.stdout.decode().split(maxsplit=1)[0]
        if len(value) != 64:
            raise ImageResizeError("resized image SHA-256 is invalid")
        return value

    def _run(self, host_id: str, command: CommandSpec, timeout: int) -> CommandResult:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise ImageResizeError("target host not found")
            sudo = host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
        return self.executor.run(
            host_id,
            command,
            sudo=sudo,
            timeout=timeout,
            env={"LC_ALL": "C"},
        )


def _validate_path(value: str) -> None:
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts or "\0" in value:
        raise ImageResizeError("target image path is invalid")


def _require(result: CommandResult, message: str) -> None:
    if result.exit_code or result.timed_out or result.cancelled:
        raise ImageResizeError(message)
