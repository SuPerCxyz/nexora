"""Structured NUMA and CPUTune change adapters over the persistent VM XML plan service."""

from dataclasses import asdict
from typing import Any

from nexora.resources.conflicts import ResourceBaseVersion
from nexora.vms.cpu_changes import VmChangePreview, VmCpuChangeService
from nexora.xml import (
    AdvancedDeviceChange,
    CpuTuneChange,
    LibvirtXmlDocument,
    NumaChange,
    apply_advanced_device_change,
    apply_cputune_change,
    apply_numa_change,
    read_cpu_topology,
    read_memory_config,
)


class VmNumaChangeService(VmCpuChangeService):
    def preview_numa(
        self,
        base: ResourceBaseVersion,
        change: NumaChange,
    ) -> VmChangePreview:
        current, original_xml, original_hash = self._current_persistent(base)
        document = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        topology = read_cpu_topology(document)
        memory = read_memory_config(document)
        change.validate(max_vcpus=topology.maximum_vcpus, memory_kib=memory.maximum_kib)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_numa_change(
            proposed,
            change,
            max_vcpus=topology.maximum_vcpus,
            memory_kib=memory.maximum_kib,
        )
        return self._create_preview(
            base,
            "numa_config",
            asdict(change, dict_factory=_serialize),
            current,
            proposed,
            original_xml,
            original_hash,
        )


class VmCpuTuneChangeService(VmCpuChangeService):
    def preview_cputune(
        self,
        base: ResourceBaseVersion,
        change: CpuTuneChange,
    ) -> VmChangePreview:
        current, original_xml, original_hash = self._current_persistent(base)
        document = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        topology = read_cpu_topology(document)
        change.validate(max_vcpus=topology.maximum_vcpus)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_cputune_change(proposed, change, max_vcpus=topology.maximum_vcpus)
        return self._create_preview(
            base,
            "cputune_config",
            asdict(change, dict_factory=_serialize),
            current,
            proposed,
            original_xml,
            original_hash,
        )


class VmAdvancedDeviceChangeService(VmCpuChangeService):
    def preview_devices(
        self,
        base: ResourceBaseVersion,
        change: AdvancedDeviceChange,
    ) -> VmChangePreview:
        current, original_xml, original_hash = self._current_persistent(base)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_advanced_device_change(proposed, change)
        return self._create_preview(
            base,
            "advanced_devices",
            asdict(change),
            current,
            proposed,
            original_xml,
            original_hash,
        )


def _serialize(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if hasattr(value, "__dataclass_fields__"):
            result[key] = asdict(value, dict_factory=_serialize)
        elif isinstance(value, list):
            result[key] = [
                asdict(v, dict_factory=_serialize) if hasattr(v, "__dataclass_fields__") else v
                for v in value
            ]
        else:
            result[key] = value
    return result
