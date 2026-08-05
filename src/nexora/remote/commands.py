"""Typed remote command specifications."""

import re
import shlex
from dataclasses import dataclass
from typing import Protocol

PROGRAM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}$")
ENVIRONMENT_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")


class RemoteCommand(Protocol):
    """A command that can provide an argv without shell fragments."""

    def argv(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class CommandSpec:
    """A validated executable and argument tuple."""

    program: str
    arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not PROGRAM_PATTERN.fullmatch(self.program):
            raise ValueError("invalid remote program")
        if any("\0" in argument or len(argument) > 4_096 for argument in self.arguments):
            raise ValueError("invalid remote argument")

    def argv(self) -> tuple[str, ...]:
        return (self.program, *self.arguments)


def render_remote_command(
    command: RemoteCommand,
    *,
    sudo: bool,
    environment: dict[str, str] | None,
) -> str:
    """Render validated argv using one POSIX quoting implementation."""

    argv = list(command.argv())
    if not argv:
        raise ValueError("remote command cannot be empty")
    if environment:
        assignments: list[str] = []
        for name in sorted(environment):
            if not ENVIRONMENT_PATTERN.fullmatch(name):
                raise ValueError("invalid environment variable name")
            value = environment[name]
            if "\0" in value or len(value) > 4_096:
                raise ValueError("invalid environment variable value")
            assignments.append(f"{name}={value}")
        argv = ["env", "--", *assignments, *argv]
    if sudo:
        argv = ["sudo", "-n", "--", *argv]
    return shlex.join(argv)
