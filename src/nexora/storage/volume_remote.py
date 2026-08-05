"""Audited remote commands for writable storage volumes."""

from nexora.db import Database
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.storage.remote_ops import StoragePoolRemoteCommands, require_success


class StorageVolumeRemoteCommands:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.executor = executor
        self.pool_commands = StoragePoolRemoteCommands(database, executor)

    def validate_xml(self, host_id: str, content: bytes) -> None:
        result = self.executor.run(
            host_id,
            CommandSpec("virt-xml-validate", ("-", "storagevol")),
            sudo=self.pool_commands.uses_sudo(host_id),
            timeout=30,
            stdin=content,
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        require_success(result, "storage volume XML failed schema validation")

    def virsh(
        self,
        host_id: str,
        arguments: tuple[str, ...],
        *,
        stdin: bytes | None = None,
    ) -> CommandResult:
        return self.pool_commands.virsh(host_id, arguments, stdin=stdin)
