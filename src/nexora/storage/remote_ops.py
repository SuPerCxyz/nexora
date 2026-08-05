"""Audited remote commands used by writable storage pool operations."""

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor


class StoragePoolRemoteCommands:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.database = database
        self.executor = executor

    def validate_xml(self, host_id: str, content: bytes) -> None:
        result = self.executor.run(
            host_id,
            CommandSpec("virt-xml-validate", ("-", "storagepool")),
            sudo=self.uses_sudo(host_id),
            timeout=30,
            stdin=content,
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        require_success(result, "storage pool XML failed schema validation")

    def virsh(
        self,
        host_id: str,
        arguments: tuple[str, ...],
        *,
        stdin: bytes | None = None,
    ) -> CommandResult:
        host = self._host(host_id)
        return self.executor.run(
            host_id,
            CommandSpec("virsh", ("-c", host.libvirt_uri, *arguments)),
            sudo=_uses_sudo(host),
            timeout=60,
            stdin=stdin,
            env={"LC_ALL": "C"},
            sensitive=stdin is not None,
        )

    def path_is_directory(self, host_id: str, path: str) -> bool:
        result = self.executor.run(
            host_id,
            CommandSpec("test", ("-d", path)),
            sudo=self.uses_sudo(host_id),
            timeout=15,
            env={"LC_ALL": "C"},
        )
        if result.exit_code == 0 and not result.timed_out:
            return True
        if result.exit_code == 1 and not result.timed_out:
            return False
        raise RuntimeError("storage target directory precheck failed")

    def remove_empty_directory(self, host_id: str, path: str) -> None:
        result = self.executor.run(
            host_id,
            CommandSpec("rmdir", ("--", path)),
            sudo=self.uses_sudo(host_id),
            timeout=15,
            env={"LC_ALL": "C"},
        )
        require_success(result, "task-created empty storage target cleanup failed")

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise ValueError("host not found")
            return host

    def uses_sudo(self, host_id: str) -> bool:
        return _uses_sudo(self._host(host_id))


def require_success(result: CommandResult, message: str) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise RuntimeError(message)


def _uses_sudo(host: Host) -> bool:
    return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
