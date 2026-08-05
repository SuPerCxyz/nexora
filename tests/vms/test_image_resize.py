from datetime import UTC, datetime

import pytest

from nexora.config import Settings
from nexora.db import Database
from nexora.db.migrations import upgrade_database
from nexora.hosts.models import AuthenticationMethod, Host, HostStatus, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult
from nexora.vms.image_resize import ImageResizeError, ImageResizeRemote


class Executor:
    def __init__(self) -> None:
        self.size = 1024
        self.commands: list[CommandSpec] = []

    def run(self, _host_id: str, command: CommandSpec, **_kwargs: object) -> CommandResult:
        self.commands.append(command)
        if command.program == "test":
            return _result()
        if command.program == "qemu-img" and command.arguments[0] == "info":
            return _result(f'{{"virtual-size":{self.size}}}'.encode())
        if command.program == "qemu-img" and command.arguments[0] == "resize":
            self.size = int(command.arguments[-1])
            return _result()
        if command.program == "sha256sum":
            return _result(("a" * 64 + "  image\n").encode())
        raise AssertionError(command)


def test_image_resize_uses_fixed_argv_and_verifies_growth(settings: Settings) -> None:
    database = Database(settings)
    upgrade_database(database)
    _seed_host(database)
    executor = Executor()
    remote = ImageResizeRemote(database, executor)  # type: ignore[arg-type]

    remote.grow("host-1", "/images/system.qcow2", 1024, 2048)

    resize = next(command for command in executor.commands if command.arguments[0] == "resize")
    assert ("resize", "--", "/images/system.qcow2", "2048") == resize.arguments
    assert 2048 == remote.virtual_size("host-1", "/images/system.qcow2")
    assert "a" * 64 == remote.sha256("host-1", "/images/system.qcow2")
    database.dispose()


def test_image_resize_rejects_path_traversal(settings: Settings) -> None:
    database = Database(settings)
    upgrade_database(database)
    _seed_host(database)
    remote = ImageResizeRemote(database, Executor())  # type: ignore[arg-type]
    with pytest.raises(ImageResizeError, match="path"):
        remote.virtual_size("host-1", "/images/../etc/passwd")
    database.dispose()


def _seed_host(database: Database) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(
            Host(
                id="host-1",
                name="node",
                address="node.example.test",
                ssh_port=22,
                ssh_username="root",
                authentication_method=AuthenticationMethod.PRIVATE_KEY,
                sudo_mode=SudoMode.NONE,
                libvirt_uri="qemu:///system",
                status=HostStatus.READY,
                labels_json="[]",
                created_at=now,
                updated_at=now,
            )
        )


def _result(stdout: bytes = b"") -> CommandResult:
    return CommandResult("operation", 0, stdout, b"", False, False, False, False, 0.1)
