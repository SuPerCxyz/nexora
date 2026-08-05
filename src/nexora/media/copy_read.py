"""Eligible indexed storage targets for platform image copies."""

import json
from dataclasses import dataclass

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.models import Host
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType


@dataclass(frozen=True)
class MediaCopyTarget:
    pool: ResourceIndex
    host: Host
    target_path: str


class MediaCopyTargetService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_targets(self) -> list[MediaCopyTarget]:
        statement = (
            select(ResourceIndex, Host)
            .join(Host, Host.id == ResourceIndex.host_id)
            .where(
                ResourceIndex.resource_type == ResourceType.STORAGE_POOL,
                ResourceIndex.status == ResourceStatus.MANAGED,
            )
            .order_by(Host.name, ResourceIndex.display_name)
        )
        targets: list[MediaCopyTarget] = []
        with self.database.session() as session:
            for pool, host in session.execute(statement):
                details = _details(pool.details_json)
                path = details.get("target_path")
                if (
                    details.get("pool_type") in {"dir", "netfs"}
                    and details.get("active") is True
                    and isinstance(path, str)
                ):
                    targets.append(MediaCopyTarget(pool, host, path))
        return targets


def _details(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
