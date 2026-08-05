"""Audited remote creation and recovery verification of NoCloud seed ISO."""

import base64
import re
from pathlib import PurePosixPath

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.vms.cloud_init import CloudInitDocuments

TASK_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
GENERATE_SCRIPT = b"""set -eu
final=$1
partial=$2
work=$3
umask 077
cleanup() {
  rm -rf -- "$work"
  rm -f -- "$partial"
}
trap cleanup EXIT HUP INT TERM
mkdir -m 0700 -- "$work"
printf '%s' "$NEXORA_USER_DATA_B64" | base64 -d > "$work/user-data"
printf '%s' "$NEXORA_META_DATA_B64" | base64 -d > "$work/meta-data"
printf '%s' "$NEXORA_NETWORK_CONFIG_B64" | base64 -d > "$work/network-config"
if command -v genisoimage >/dev/null 2>&1; then
  iso_tool=genisoimage
elif command -v mkisofs >/dev/null 2>&1; then
  iso_tool=mkisofs
else
  exit 42
fi
"$iso_tool" -quiet -R -J -V cidata -o "$partial" \
  "$work/user-data" "$work/meta-data" "$work/network-config"
ln -- "$partial" "$final"
rm -- "$partial"
"""
VERIFY_SCRIPT = b"""set -eu
image=$1
work=$2
umask 077
trap 'rm -rf -- "$work"' EXIT HUP INT TERM
mkdir -m 0700 -- "$work"
if command -v xorriso >/dev/null 2>&1; then
  for name in user-data meta-data network-config; do
    xorriso -osirrox on -indev "$image" -extract "/$name" "$work/$name" \
      >/dev/null 2>&1
  done
elif command -v isoinfo >/dev/null 2>&1; then
  for name in user-data meta-data network-config; do
    isoinfo -R -i "$image" -x "/$name" > "$work/$name"
  done
else
  exit 43
fi
sha256sum "$work/user-data" "$work/meta-data" "$work/network-config"
"""
PROBE_SCRIPT = b"""set -eu
(command -v genisoimage >/dev/null 2>&1 || command -v mkisofs >/dev/null 2>&1)
(command -v xorriso >/dev/null 2>&1 || command -v isoinfo >/dev/null 2>&1)
"""


class CloudInitRemoteError(RuntimeError):
    pass


class CloudInitRemote:
    def __init__(self, database: Database, executor: RemoteExecutor) -> None:
        self.database = database
        self.executor = executor

    def probe(self, host_id: str) -> None:
        result = self.executor.run(
            host_id,
            CommandSpec("bash", ("-s",)),
            sudo=self._sudo(host_id),
            timeout=15,
            stdin=PROBE_SCRIPT,
            env={"LC_ALL": "C"},
        )
        _require(result, "cloud-init ISO tools are unavailable on the target node")

    def publish(
        self,
        host_id: str,
        final_path: str,
        documents: CloudInitDocuments,
        *,
        task_id: str,
    ) -> str:
        _validate(final_path, task_id)
        partial = f"{final_path}.nexora-{task_id}.partial"
        work = f"/var/tmp/nexora-cloudinit-{task_id}"
        if self._exists(host_id, final_path):
            self.verify(host_id, final_path, documents, task_id=task_id)
            return final_path
        result = self.executor.run(
            host_id,
            CommandSpec("bash", ("-s", "--", final_path, partial, work)),
            sudo=self._sudo(host_id),
            timeout=120,
            stdin=GENERATE_SCRIPT,
            env={
                "LC_ALL": "C",
                "NEXORA_USER_DATA_B64": _encode(documents.user_data),
                "NEXORA_META_DATA_B64": _encode(documents.meta_data),
                "NEXORA_NETWORK_CONFIG_B64": _encode(documents.network_config),
            },
            sensitive=True,
        )
        _require(result, "cloud-init seed generation failed")
        self.verify(host_id, final_path, documents, task_id=task_id)
        return final_path

    def verify(
        self,
        host_id: str,
        path: str,
        documents: CloudInitDocuments,
        *,
        task_id: str,
    ) -> None:
        _validate(path, task_id)
        work = f"/var/tmp/nexora-cloudinit-verify-{task_id}"
        result = self.executor.run(
            host_id,
            CommandSpec("bash", ("-s", "--", path, work)),
            sudo=self._sudo(host_id),
            timeout=60,
            stdin=VERIFY_SCRIPT,
            env={"LC_ALL": "C"},
            sensitive=True,
        )
        _require(result, "cloud-init seed verification failed")
        actual = tuple(line.split(maxsplit=1)[0] for line in result.stdout.decode().splitlines())
        if actual != documents.digests:
            raise CloudInitRemoteError("cloud-init seed collision or content mismatch")

    def _exists(self, host_id: str, path: str) -> bool:
        result = self.executor.run(
            host_id,
            CommandSpec("test", ("-e", path)),
            sudo=self._sudo(host_id),
            timeout=15,
            env={"LC_ALL": "C"},
        )
        if result.exit_code not in {0, 1} or result.timed_out or result.cancelled:
            raise CloudInitRemoteError("cloud-init seed existence check failed")
        return result.exit_code == 0

    def _sudo(self, host_id: str) -> bool:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise CloudInitRemoteError("host not found")
            return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS


def _validate(path: str, task_id: str) -> None:
    parsed = PurePosixPath(path)
    if (
        not parsed.is_absolute()
        or ".." in parsed.parts
        or not path.endswith(".iso")
        or TASK_ID.fullmatch(task_id) is None
    ):
        raise CloudInitRemoteError("cloud-init seed path or task identity is invalid")


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _require(result: CommandResult, message: str) -> None:
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.stdout_truncated
        or result.stderr_truncated
    ):
        raise CloudInitRemoteError(message)
