"""Strict discovery and cleanup of Nexora-owned transient remote entities."""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor

TEMP_ROOTS = (PurePosixPath("/run"), PurePosixPath("/tmp"), PurePosixPath("/var/tmp"))
UNIT_PATTERN = re.compile(r"^nexora-[A-Za-z0-9_.@-]{1,128}\.(?:service|timer|scope)$")
MAX_ENTITIES = 1_000


class RemovalInventoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteCleanupInventory:
    paths: tuple[str, ...]
    units: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class RemoteCleanupService:
    def __init__(self, executor: RemoteExecutor) -> None:
        self.executor = executor

    def discover(self, host_id: str, *, sudo: bool) -> RemoteCleanupInventory:
        path_result = self._run(
            host_id,
            CommandSpec(
                "find",
                (
                    "/run",
                    "/tmp",
                    "/var/tmp",
                    "-xdev",
                    "-maxdepth",
                    "3",
                    "-name",
                    "nexora-*",
                    "-print",
                ),
            ),
            sudo=sudo,
        )
        _require(path_result, "temporary entity discovery")
        paths = _parse_paths(path_result.stdout)
        unit_result = self._run(
            host_id,
            CommandSpec(
                "systemctl",
                ("list-units", "--all", "--plain", "--no-legend", "nexora-*"),
            ),
            sudo=sudo,
        )
        warnings: tuple[str, ...] = ()
        if _successful(unit_result):
            units = _parse_units(unit_result.stdout)
        else:
            units = ()
            warnings = ("systemd transient-unit inventory is unavailable",)
        return RemoteCleanupInventory(paths, units, warnings)

    def cleanup(
        self,
        host_id: str,
        inventory: RemoteCleanupInventory,
        *,
        sudo: bool,
    ) -> None:
        for unit in inventory.units:
            _validate_unit(unit)
            result = self._run(
                host_id,
                CommandSpec("systemctl", ("stop", unit)),
                sudo=sudo,
            )
            _require(result, "transient unit cleanup")
        for value in inventory.paths:
            path = _validate_path(value)
            result = self._run(
                host_id,
                CommandSpec("find", (str(path), "-xdev", "-depth", "-delete")),
                sudo=sudo,
            )
            _require(result, "temporary path cleanup")

    def _run(
        self,
        host_id: str,
        command: CommandSpec,
        *,
        sudo: bool,
    ) -> CommandResult:
        return self.executor.run(
            host_id,
            command,
            sudo=sudo,
            timeout=30,
            env={"LC_ALL": "C"},
        )


def _parse_paths(content: bytes) -> tuple[str, ...]:
    values = tuple(line for line in content.decode("utf-8").splitlines() if line)
    if len(values) > MAX_ENTITIES:
        raise RemovalInventoryError("temporary entity count exceeds safety limit")
    paths = tuple(str(_validate_path(value)) for value in values)
    if len(paths) != len(set(paths)):
        raise RemovalInventoryError("temporary entity inventory contains duplicates")
    return tuple(sorted(paths))


def _validate_path(value: str) -> PurePosixPath:
    if "\0" in value or len(value) > 4_096:
        raise RemovalInventoryError("invalid temporary entity path")
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts or not path.name.startswith("nexora-"):
        raise RemovalInventoryError("temporary entity escaped the Nexora prefix")
    if not any(root in path.parents for root in TEMP_ROOTS):
        raise RemovalInventoryError("temporary entity escaped allowed roots")
    return path


def _parse_units(content: bytes) -> tuple[str, ...]:
    values = tuple(
        line.split(maxsplit=1)[0] for line in content.decode("utf-8").splitlines() if line.strip()
    )
    if len(values) > MAX_ENTITIES:
        raise RemovalInventoryError("transient unit count exceeds safety limit")
    for value in values:
        _validate_unit(value)
    if len(values) != len(set(values)):
        raise RemovalInventoryError("transient unit inventory contains duplicates")
    return tuple(sorted(values))


def _validate_unit(value: str) -> None:
    if UNIT_PATTERN.fullmatch(value) is None:
        raise RemovalInventoryError("invalid Nexora transient unit name")


def _successful(result: CommandResult) -> bool:
    return (
        result.exit_code == 0
        and not result.timed_out
        and not result.cancelled
        and not result.stdout_truncated
        and not result.stderr_truncated
    )


def _require(result: CommandResult, label: str) -> None:
    if not _successful(result):
        raise RemovalInventoryError(f"{label} failed or returned incomplete output")
