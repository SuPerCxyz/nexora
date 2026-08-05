"""Structured memory change adapter over the persistent VM XML plan service."""

from dataclasses import asdict

from nexora.resources.conflicts import ResourceBaseVersion
from nexora.vms.cpu_changes import VmChangePreview, VmCpuChangeService
from nexora.xml import LibvirtXmlDocument, MemoryConfigChange, apply_memory_config


class VmMemoryChangeService(VmCpuChangeService):
    def preview_memory(
        self,
        base: ResourceBaseVersion,
        change: MemoryConfigChange,
    ) -> VmChangePreview:
        change.validate()
        current, original_xml, original_hash = self._current_persistent(base)
        proposed = LibvirtXmlDocument.parse(original_xml, expected_root="domain")
        apply_memory_config(proposed, change)
        return self._create_preview(
            base,
            "memory_config",
            asdict(change),
            current,
            proposed,
            original_xml,
            original_hash,
        )
