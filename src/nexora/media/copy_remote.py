"""Remote target validation and no-clobber image publication."""

from pathlib import PurePosixPath

from nexora.media.copy_errors import MediaCopyError
from nexora.media.models import MediaItem
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor

MINIMUM_HEADROOM = 64 * 1024 * 1024


class RemoteImageTarget:
    def __init__(self, executor: RemoteExecutor) -> None:
        self.executor = executor

    def prepare(
        self,
        host_id: str,
        target_directory: PurePosixPath,
        final_path: str,
        partial_path: str,
        media: MediaItem,
        sudo: bool,
    ) -> bool:
        self._command(
            host_id,
            CommandSpec("test", ("-d", str(target_directory))),
            sudo=sudo,
            timeout=15,
            label="target directory check",
        )
        final_exists = self._exists(host_id, final_path, sudo)
        partial_exists = self._exists(host_id, partial_path, sudo)
        if final_exists:
            if partial_exists:
                self._remove(host_id, partial_path, sudo, "interrupted partial cleanup")
            if not self.size_matches(host_id, final_path, media, sudo):
                raise MediaCopyError("target file collision")
            if not self.sha256_matches(host_id, final_path, media, sudo):
                raise MediaCopyError("target file collision")
            return True
        if partial_exists:
            self._remove(host_id, partial_path, sudo, "interrupted partial cleanup")
            if self._exists(host_id, partial_path, sudo):
                raise MediaCopyError("interrupted partial cleanup failed")
        available = self._command(
            host_id,
            CommandSpec("df", ("-P", "-B1", "--", str(target_directory))),
            sudo=sudo,
            timeout=15,
            label="target free-space check",
        )
        if _available_bytes(available.stdout) < media.size_bytes + MINIMUM_HEADROOM:
            raise MediaCopyError("target storage does not have enough free space")
        return False

    def size_matches(
        self,
        host_id: str,
        path: str,
        media: MediaItem,
        sudo: bool,
    ) -> bool:
        result = self._command(
            host_id,
            CommandSpec("stat", ("-c", "%s", "--", path)),
            sudo=sudo,
            timeout=30,
            label="remote file size",
        )
        try:
            return int(result.stdout.strip()) == media.size_bytes
        except ValueError as exc:
            raise MediaCopyError("remote file size is invalid") from exc

    def sha256_matches(
        self,
        host_id: str,
        path: str,
        media: MediaItem,
        sudo: bool,
    ) -> bool:
        result = self._command(
            host_id,
            CommandSpec("sha256sum", ("--", path)),
            sudo=sudo,
            timeout=86_400,
            label="remote SHA-256",
        )
        digest = result.stdout.decode(errors="strict").split(maxsplit=1)[0]
        if len(digest) != 64:
            raise MediaCopyError("remote SHA-256 output is invalid")
        return digest == media.sha256

    def publish(
        self,
        host_id: str,
        partial_path: str,
        final_path: str,
        media: MediaItem,
        sudo: bool,
    ) -> None:
        self._command(
            host_id,
            CommandSpec("ln", ("--", partial_path, final_path)),
            sudo=sudo,
            timeout=30,
            label="no-clobber image publish",
        )
        if not self.size_matches(host_id, final_path, media, sudo):
            raise MediaCopyError("published image verification failed")
        self._remove(host_id, partial_path, sudo, "published partial cleanup")

    def cleanup_partial(self, host_id: str, path: str, sudo: bool) -> None:
        try:
            self._command(
                host_id,
                CommandSpec("rm", ("-f", "--", path)),
                sudo=sudo,
                timeout=30,
                label="partial image cleanup",
            )
        except MediaCopyError:
            return

    def _exists(self, host_id: str, path: str, sudo: bool) -> bool:
        result = self.executor.run(
            host_id,
            CommandSpec("test", ("-e", path)),
            sudo=sudo,
            timeout=15,
            env={"LC_ALL": "C"},
        )
        if (
            result.exit_code not in {0, 1}
            or result.timed_out
            or result.cancelled
            or result.stdout_truncated
            or result.stderr_truncated
        ):
            raise MediaCopyError("target file existence check failed")
        return result.exit_code == 0

    def _remove(self, host_id: str, path: str, sudo: bool, label: str) -> None:
        self._command(
            host_id,
            CommandSpec("rm", ("--", path)),
            sudo=sudo,
            timeout=30,
            label=label,
        )

    def _command(
        self,
        host_id: str,
        command: CommandSpec,
        *,
        sudo: bool,
        timeout: int,
        label: str,
    ) -> CommandResult:
        result = self.executor.run(
            host_id,
            command,
            sudo=sudo,
            timeout=timeout,
            env={"LC_ALL": "C"},
        )
        if (
            result.exit_code != 0
            or result.timed_out
            or result.cancelled
            or result.stdout_truncated
            or result.stderr_truncated
        ):
            raise MediaCopyError(f"{label} failed")
        return result


def _available_bytes(output: bytes) -> int:
    lines = [line.split() for line in output.decode(errors="strict").splitlines() if line.strip()]
    if len(lines) < 2 or len(lines[-1]) < 4:
        raise MediaCopyError("target free-space output is invalid")
    try:
        return int(lines[-1][3])
    except ValueError as exc:
        raise MediaCopyError("target free-space output is invalid") from exc
