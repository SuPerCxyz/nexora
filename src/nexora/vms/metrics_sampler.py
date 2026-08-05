"""Single-process low-frequency host and VM metrics sampler."""

import asyncio
import logging
from contextlib import suppress

from sqlalchemy import select

from nexora.db import Database
from nexora.hosts.metrics import HostMetricsError, HostMetricsService
from nexora.hosts.metrics_history import HostMetricsHistoryStore
from nexora.hosts.models import Host, HostStatus
from nexora.resources.models import ResourceIndex, ResourceStatus, ResourceType
from nexora.vms.metrics import VmMetricsError, VmMetricsService
from nexora.vms.metrics_history import MetricsHistoryStore

LOG = logging.getLogger(__name__)


class MetricsSampler:
    def __init__(
        self,
        database: Database,
        host_service: HostMetricsService,
        vm_service: VmMetricsService,
        *,
        interval_seconds: int = 360,
    ) -> None:
        self.database = database
        self.host_service = host_service
        self.vm_service = vm_service
        self.host_history = HostMetricsHistoryStore(database)
        self.vm_history = MetricsHistoryStore(database)
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="nexora-metrics-sampler")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def run_once(self) -> None:
        for host_id, vm_uuids in self._targets():
            await self._sample_host(host_id)
            for vm_uuid in vm_uuids:
                await self._sample_vm(host_id, vm_uuid)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stopping.wait(), self.interval_seconds)
            except TimeoutError:
                continue

    async def _sample_host(self, host_id: str) -> None:
        try:
            metrics = await asyncio.to_thread(self.host_service.sample, host_id)
            await asyncio.to_thread(self.host_history.record, host_id, metrics)
        except HostMetricsError:
            LOG.info("host metrics sample unavailable", extra={"host_id": host_id})

    async def _sample_vm(self, host_id: str, vm_uuid: str) -> None:
        try:
            metrics = await asyncio.to_thread(self.vm_service.sample, host_id, vm_uuid)
            await asyncio.to_thread(self.vm_history.record_metrics, host_id, vm_uuid, metrics)
        except VmMetricsError:
            LOG.info("VM metrics sample unavailable", extra={"host_id": host_id})

    def _targets(self) -> list[tuple[str, list[str]]]:
        with self.database.session() as session:
            hosts = list(
                session.scalars(
                    select(Host).where(Host.status.in_([HostStatus.READY, HostStatus.DEGRADED]))
                )
            )
            targets: list[tuple[str, list[str]]] = []
            for host in hosts[:500]:
                vm_uuids = list(
                    session.scalars(
                        select(ResourceIndex.native_id)
                        .where(
                            ResourceIndex.host_id == host.id,
                            ResourceIndex.resource_type == ResourceType.VIRTUAL_MACHINE,
                            ResourceIndex.status != ResourceStatus.MISSING,
                        )
                        .limit(2_000)
                    )
                )
                targets.append((host.id, vm_uuids))
            return targets
