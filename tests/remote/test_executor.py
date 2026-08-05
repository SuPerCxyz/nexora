from pathlib import Path

from nexora.remote.commands import CommandSpec
from nexora.remote.executor import RemoteCommandAudit, RemoteExecutor
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile


class Resolver:
    def __init__(self, connection: SSHConnection) -> None:
        self.connection = connection

    def resolve(self, host_id: str) -> SSHConnectionProfile:
        assert "host-1" == host_id
        return SSHConnectionProfile(self.connection)


class AuditCollector:
    def __init__(self) -> None:
        self.events: list[RemoteCommandAudit] = []

    def record(self, event: RemoteCommandAudit) -> None:
        self.events.append(event)


class ProcessRunner:
    def __init__(self) -> None:
        self.argv: list[str] = []

    def run(self, argv: list[str], **_kwargs: object) -> ProcessResult:
        self.argv = argv
        return ProcessResult(
            exit_code=0,
            stdout=b"secret output",
            stderr=b"",
            stdout_truncated=False,
            stderr_truncated=False,
            timed_out=False,
            cancelled=False,
            duration_seconds=0.1,
        )


def test_executor_builds_ssh_and_records_operation(tmp_path: Path) -> None:
    connection = SSHConnection(
        "kvm.example.test",
        22,
        "root",
        (tmp_path / "known_hosts").absolute(),
    )
    audit = AuditCollector()
    runner = ProcessRunner()
    executor = RemoteExecutor(Resolver(connection), audit, process_runner=runner)

    result = executor.run(
        "host-1",
        CommandSpec("virsh", ("list", "--all")),
        operation_id="operation-1",
    )

    assert "operation-1" == result.operation_id
    assert "StrictHostKeyChecking=yes" in runner.argv
    assert "virsh list --all" == runner.argv[-1]
    assert "secret output" == audit.events[0].stdout_summary


def test_sensitive_execution_redacts_command_and_output(tmp_path: Path) -> None:
    connection = SSHConnection(
        "kvm.example.test",
        22,
        "root",
        (tmp_path / "known_hosts").absolute(),
    )
    audit = AuditCollector()
    runner = ProcessRunner()
    executor = RemoteExecutor(Resolver(connection), audit, process_runner=runner)

    executor.run(
        "host-1",
        CommandSpec("printenv", ("PASSWORD",)),
        sensitive=True,
    )

    assert "[sensitive command]" == audit.events[0].command_summary
    assert "" == audit.events[0].stdout_summary
    assert "" == audit.events[0].stderr_summary
