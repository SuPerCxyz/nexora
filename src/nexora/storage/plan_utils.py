"""Pure helpers shared by persistent storage pool plans."""

import difflib
import json
from collections.abc import Callable

from nexora.resources.models import ResourceIndex
from nexora.storage.contracts import StoragePoolCreateInput


def creation_diff(content: bytes) -> str:
    lines = content.decode().splitlines(keepends=True)
    return "".join(difflib.unified_diff([], lines, fromfile="/dev/null", tofile="pool.xml"))


def matches_create(resource: ResourceIndex, create: StoragePoolCreateInput) -> bool:
    details = json.loads(resource.details_json)
    if (
        resource.display_name != create.name
        or details.get("pool_type") != create.pool_type
        or details.get("target_path") != create.target_path
    ):
        return False
    if create.pool_type == "dir":
        return True
    return (
        details.get("source_host") == create.source_host
        and details.get("source_path") == create.source_path
        and details.get("nfs_version") == create.nfs_version
        and set(details.get("mount_options", [])) == set(create.mount_options)
    )


def error_message(error: Exception, rollback_error: str | None) -> str:
    if rollback_error is None:
        return str(error)
    return f"{error}; rollback failed: {rollback_error}"


def notify(
    progress: Callable[[int, str], None] | None,
    sequence: int,
    message: str,
) -> None:
    if progress is not None:
        progress(sequence, message)
