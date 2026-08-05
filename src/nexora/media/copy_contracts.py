"""Validated persistent input for a remote platform-image copy."""

import json
import re
from dataclasses import dataclass

COPY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,250}\.(qcow2|raw)$")


@dataclass(frozen=True)
class MediaCopyInput:
    media_item_id: str
    media_sha256: str
    host_id: str
    pool_resource_id: str
    pool_native_id: str
    pool_generation: int
    pool_persistent_hash: str
    target_file_name: str

    def encode(self) -> str:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, value: str | None) -> "MediaCopyInput":
        if value is None or len(value) > 8_192:
            raise ValueError("media copy input is unavailable")
        try:
            payload = json.loads(value)
            result = cls(
                media_item_id=str(payload["media_item_id"]),
                media_sha256=str(payload["media_sha256"]),
                host_id=str(payload["host_id"]),
                pool_resource_id=str(payload["pool_resource_id"]),
                pool_native_id=str(payload["pool_native_id"]),
                pool_generation=int(payload["pool_generation"]),
                pool_persistent_hash=str(payload["pool_persistent_hash"]),
                target_file_name=str(payload["target_file_name"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("media copy input is invalid") from exc
        result.validate()
        return result

    def validate(self) -> None:
        if not all(
            (
                self.media_item_id,
                self.host_id,
                self.pool_resource_id,
                self.pool_native_id,
                self.pool_persistent_hash,
            )
        ):
            raise ValueError("media copy input is invalid")
        if (
            self.pool_generation < 1
            or len(self.media_sha256) != 64
            or not COPY_NAME.fullmatch(self.target_file_name)
        ):
            raise ValueError("media copy input is invalid")
