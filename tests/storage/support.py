"""Reusable fake remote storage pool backend."""

import shlex
from pathlib import Path
from threading import Event

from lxml import etree

from nexora.remote.executor import RemoteCommandAudit
from nexora.remote.process import ProcessResult
from nexora.remote.ssh import SSHConnection, SSHConnectionProfile


class Resolver:
    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def resolve(self, _host_id: str) -> SSHConnectionProfile:
        return SSHConnectionProfile(SSHConnection("node", 22, "root", self.known_hosts))


class Audit:
    def record(self, _event: RemoteCommandAudit) -> None:
        return


class EmptyDomainDiscovery:
    def run(self, _host_id: str) -> None:
        return


class PoolBackend:
    def __init__(self) -> None:
        self.xml: bytes | None = None
        self.active = False
        self.autostart = False
        self.target_exists = False
        self.volumes: dict[str, bytes] = {}

    def run(
        self,
        _profile: SSHConnectionProfile,
        command: str,
        *,
        timeout: int,
        stdin: bytes | None,
        cancel_event: Event | None,
    ) -> ProcessResult:
        del timeout, cancel_event
        if "virt-xml-validate" in command:
            return result()
        if "pool-list --all --name" in command:
            return result(self._name())
        if "pool-define" in command:
            assert stdin is not None
            self.xml = stdin
            return result()
        if "test -d" in command:
            return result(exit_code=0 if self.target_exists else 1)
        if "pool-build" in command:
            self.target_exists = True
            return result()
        if "rmdir --" in command:
            self.target_exists = False
            return result()
        if "pool-start" in command:
            self.active = True
            return result()
        if "pool-autostart" in command:
            self.autostart = "--disable" not in command
            return result()
        if "pool-refresh" in command:
            return result()
        if "vol-create" in command:
            assert stdin is not None
            root = etree.fromstring(stdin)
            name = root.findtext("name")
            assert name is not None and name not in self.volumes
            self.volumes[name] = stdin
            return result()
        if "vol-resize" in command:
            name = next(item for item in self.volumes if item in command)
            root = etree.fromstring(self.volumes[name])
            capacity = root.find("capacity")
            assert capacity is not None
            arguments = shlex.split(command)
            capacity.text = arguments[arguments.index("vol-resize") + 2]
            self.volumes[name] = etree.tostring(root)
            return result()
        if "vol-delete" in command:
            name = next(item for item in self.volumes if item in command)
            del self.volumes[name]
            return result()
        if "vol-dumpxml" in command:
            name = next(item for item in self.volumes if item in command)
            return result(self._volume_xml(name))
        if "vol-list" in command:
            return result(self._volume_list())
        if "pool-destroy" in command:
            if not self.active:
                return result(exit_code=1)
            self.active = False
            return result()
        if "pool-undefine" in command:
            self.xml = None
            self.autostart = False
            return result()
        if "pool-info" in command:
            return result(self._info())
        if "pool-dumpxml" in command:
            return result(self._dumpxml())
        raise AssertionError(command)

    def _name(self) -> bytes:
        if self.xml is None:
            return b""
        return f"{etree.fromstring(self.xml).findtext('name')}\n".encode()

    def _info(self) -> bytes:
        state = "running" if self.active else "inactive"
        auto = "yes" if self.autostart else "no"
        return f"State: {state}\nPersistent: yes\nAutostart: {auto}\n".encode()

    def _dumpxml(self) -> bytes:
        assert self.xml is not None
        root = etree.fromstring(self.xml)
        target = root.find("target")
        assert target is not None
        values = (("capacity", "1000"), ("allocation", "100"), ("available", "900"))
        for name, value in values:
            element = etree.Element(name, unit="bytes")
            element.text = value
            root.insert(root.index(target), element)
        return etree.tostring(root)

    def _volume_list(self) -> bytes:
        lines = [" Name                 Path", "--------------------------------------------"]
        lines.extend(f" {name:<20} /images/{name}" for name in self.volumes)
        return ("\n".join(lines) + "\n").encode()

    def _volume_xml(self, name: str) -> bytes:
        root = etree.fromstring(self.volumes[name])
        name_element = root.find("name")
        assert name_element is not None
        name_element.addnext(_text_element("key", f"/images/{name}"))
        target = root.find("target")
        assert target is not None
        target.insert(0, _text_element("path", f"/images/{name}"))
        return etree.tostring(root)


def result(stdout: bytes = b"", *, exit_code: int = 0) -> ProcessResult:
    return ProcessResult(exit_code, stdout, b"", False, False, False, False, 0.01)


def _text_element(name: str, value: str) -> etree._Element:
    element = etree.Element(name)
    element.text = value
    return element
