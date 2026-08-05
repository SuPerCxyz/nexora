from pathlib import Path

import pytest

from nexora.remote.commands import CommandSpec, render_remote_command
from nexora.remote.ssh import SSHConnection, build_ssh_argv


def test_remote_arguments_are_posix_quoted_not_executed() -> None:
    command = CommandSpec("virsh", ("dominfo", "vm; touch /tmp/injected"))

    rendered = render_remote_command(command, sudo=False, environment=None)

    assert "virsh dominfo 'vm; touch /tmp/injected'" == rendered


def test_sudo_and_environment_have_fixed_wrappers() -> None:
    command = CommandSpec("virsh", ("list", "--all"))

    rendered = render_remote_command(
        command,
        sudo=True,
        environment={"LC_ALL": "C", "VALUE": "$(id)"},
    )

    assert "sudo -n -- env -- LC_ALL=C 'VALUE=$(id)' virsh list --all" == rendered


def test_invalid_program_environment_and_nul_are_rejected() -> None:
    with pytest.raises(ValueError):
        CommandSpec("-evil")
    with pytest.raises(ValueError):
        CommandSpec("virsh", ("bad\0value",))
    with pytest.raises(ValueError):
        render_remote_command(
            CommandSpec("id"),
            sudo=False,
            environment={"BAD-NAME": "value"},
        )


def test_ssh_argv_disables_ambient_configuration_and_trust(tmp_path: Path) -> None:
    connection = SSHConnection(
        "KVM.EXAMPLE.TEST",
        10022,
        "operator",
        (tmp_path / "known_hosts").absolute(),
        (tmp_path / "identity").absolute(),
    )

    argv = build_ssh_argv(connection, CommandSpec("id"), sudo=True)

    assert ["ssh", "-F", "/dev/null"] == argv[:3]
    assert "StrictHostKeyChecking=yes" in argv
    assert "GlobalKnownHostsFile=/dev/null" in argv
    assert "UpdateHostKeys=no" in argv
    assert "ClearAllForwardings=yes" in argv
    assert argv[-3:] == ["--", "kvm.example.test", "sudo -n -- id"]


def test_ssh_connection_rejects_option_injection(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SSHConnection(
            "-oProxyCommand=evil",
            22,
            "root",
            (tmp_path / "known_hosts").absolute(),
        )
