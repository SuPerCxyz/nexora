"""Validated resource discovery contracts."""

import json
from dataclasses import dataclass, field

from nexora.resources.models import ResourceStatus

MAX_DETAILS_BYTES = 256 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class ResourceObservation:
    native_id: str
    display_name: str
    status: ResourceStatus
    persistent_hash: str | None
    live_hash: str | None
    details: dict[str, object] = field(default_factory=dict)
    documents: dict[str, bytes] = field(default_factory=dict)
    parent_native_id: str | None = None
    source: str = "unknown"
    hash_algorithm: str | None = None

    def __post_init__(self) -> None:
        if not self.native_id or len(self.native_id) > 512 or "\0" in self.native_id:
            raise ValueError("invalid native resource identity")
        if not self.display_name or len(self.display_name) > 512:
            raise ValueError("invalid resource display name")
        encoded = json.dumps(
            self.details,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if len(encoded) > MAX_DETAILS_BYTES:
            raise ValueError("resource details exceed limit")
        for kind, content in self.documents.items():
            if not kind or len(kind) > 32 or not kind.replace("_", "").isalnum():
                raise ValueError("invalid resource document kind")
            if len(content) > MAX_DOCUMENT_BYTES:
                raise ValueError("resource document exceeds limit")
