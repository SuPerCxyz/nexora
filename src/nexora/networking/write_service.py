"""Safe network write operations with rollback and confirmation window."""

import json
import re
from dataclasses import dataclass

from nexora.db import Database
from nexora.hosts.models import Host, SudoMode
from nexora.networking.change_store import (
    NetworkChangeError,
    NetworkChangePlanStore,
    NetworkChangePreview,
)
from nexora.remote.commands import CommandSpec
from nexora.remote.executor import CommandResult, RemoteExecutor
from nexora.resources.host_network_discovery import HostNetworkDiscoveryService

IFACE_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,15}$")
VLAN_ID_RANGE = range(1, 4095)


@dataclass(frozen=True)
class BridgeCreateInput:
    bridge_name: str
    attach_iface: str | None = None
    migrate_ip_cidr: str | None = None


@dataclass(frozen=True)
class VlanCreateInput:
    parent_iface: str
    vlan_id: int
    vlan_name: str | None = None


class NetworkWriteService:
    def __init__(
        self,
        database: Database,
        executor: RemoteExecutor,
        host_networks: HostNetworkDiscoveryService,
    ) -> None:
        self.database = database
        self.executor = executor
        self.host_networks = host_networks
        self.plans = NetworkChangePlanStore(database)

    def preview_bridge_create(
        self,
        host_id: str,
        change: BridgeCreateInput,
    ) -> NetworkChangePreview:
        self._validate_iface(change.bridge_name)
        if change.attach_iface is not None:
            self._validate_iface(change.attach_iface)
        self.host_networks.run(host_id)
        existing = self._existing_ifaces(host_id)
        if change.bridge_name in existing:
            raise NetworkChangeError(f"interface {change.bridge_name} already exists")
        if change.attach_iface and change.attach_iface not in existing:
            raise NetworkChangeError(f"interface {change.attach_iface} does not exist")
        rollback_parts: list[str] = [f"ip link delete {change.bridge_name}"]
        if change.attach_iface:
            rollback_parts.insert(0, f"ip link set dev {change.attach_iface} nomaster")
        rollback_script = ";\n".join(rollback_parts)
        change_input: dict[str, object] = {
            "bridge_name": change.bridge_name,
            "attach_iface": change.attach_iface,
            "migrate_ip_cidr": change.migrate_ip_cidr,
        }
        return self.plans.create(
            host_id=host_id,
            change_type="bridge_create",
            target_iface=change.bridge_name,
            change_input=change_input,
            rollback_script=rollback_script,
        )

    def preview_vlan_create(
        self,
        host_id: str,
        change: VlanCreateInput,
    ) -> NetworkChangePreview:
        self._validate_iface(change.parent_iface)
        if change.vlan_id not in VLAN_ID_RANGE:
            raise NetworkChangeError("VLAN ID must be between 1 and 4094")
        vlan_name = change.vlan_name or f"{change.parent_iface}.{change.vlan_id}"
        self._validate_iface(vlan_name)
        self.host_networks.run(host_id)
        existing = self._existing_ifaces(host_id)
        if change.parent_iface not in existing:
            raise NetworkChangeError(f"parent interface {change.parent_iface} does not exist")
        if vlan_name in existing:
            raise NetworkChangeError(f"interface {vlan_name} already exists")
        rollback_script = f"ip link delete {vlan_name}"
        change_input: dict[str, object] = {
            "parent_iface": change.parent_iface,
            "vlan_id": change.vlan_id,
            "vlan_name": vlan_name,
        }
        return self.plans.create(
            host_id=host_id,
            change_type="vlan_create",
            target_iface=vlan_name,
            change_input=change_input,
            rollback_script=rollback_script,
        )

    def execute(
        self,
        plan_id: str,
        *,
        host_id: str,
    ) -> str:
        plan = self.plans.load_confirmed(plan_id)
        if plan.host_id != host_id:
            raise NetworkChangeError("network change plan scope does not match")
        self.plans.mark_running(plan_id)
        try:
            payload = json.loads(plan.change_input_json)
            if plan.change_type == "bridge_create":
                self._execute_bridge_create(host_id, payload)
            elif plan.change_type == "vlan_create":
                self._execute_vlan_create(host_id, payload)
            else:
                raise NetworkChangeError(f"unsupported change type: {plan.change_type}")
            self.plans.mark_succeeded(plan_id)
            return f"network change {plan.change_type} succeeded; iface={plan.target_iface}"
        except Exception as exc:
            self._rollback(host_id, plan.rollback_script)
            self.plans.mark_failed(plan_id, str(exc))
            raise

    def _execute_bridge_create(self, host_id: str, payload: dict[str, object]) -> None:
        bridge_name = str(payload["bridge_name"])
        attach_iface = payload.get("attach_iface")
        self._run(
            host_id, CommandSpec("ip", ("link", "add", "name", bridge_name, "type", "bridge"))
        )
        self._run(host_id, CommandSpec("ip", ("link", "set", "dev", bridge_name, "up")))
        if attach_iface:
            self._run(
                host_id,
                CommandSpec("ip", ("link", "set", "dev", str(attach_iface), "master", bridge_name)),
            )

    def _execute_vlan_create(self, host_id: str, payload: dict[str, object]) -> None:
        vlan_name = str(payload["vlan_name"])
        parent = str(payload["parent_iface"])
        vlan_id = str(payload["vlan_id"])
        self._run(
            host_id,
            CommandSpec(
                "ip",
                ("link", "add", "link", parent, "name", vlan_name, "type", "vlan", "id", vlan_id),
            ),
        )
        self._run(host_id, CommandSpec("ip", ("link", "set", "dev", vlan_name, "up")))

    def _rollback(self, host_id: str, rollback_script: str) -> None:
        try:
            for line in rollback_script.split(";\n"):
                line = line.strip()
                if line:
                    import shlex

                    parts = shlex.split(line)
                    if parts:
                        self._run(host_id, CommandSpec(parts[0], tuple(parts[1:])))
        except Exception:
            pass

    def _existing_ifaces(self, host_id: str) -> set[str]:
        result = self._run(
            host_id,
            CommandSpec("ip", ("-o", "-j", "link", "show")),
            timeout=15,
        )
        if result.exit_code != 0:
            raise NetworkChangeError("cannot read host interfaces")
        try:
            entries = json.loads(result.stdout.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise NetworkChangeError("host interface data is invalid") from exc
        return {str(entry["ifname"]) for entry in entries if "ifname" in entry}

    def _run(
        self,
        host_id: str,
        command: CommandSpec,
        timeout: int = 30,
    ) -> CommandResult:
        host = self._host(host_id)
        return self.executor.run(
            host_id,
            command,
            sudo=_uses_sudo(host),
            timeout=timeout,
            env={"LC_ALL": "C"},
        )

    def _host(self, host_id: str) -> Host:
        with self.database.session() as session:
            host = session.get(Host, host_id)
            if host is None:
                raise NetworkChangeError("host not found")
            return host

    def _validate_iface(self, name: str) -> None:
        if not IFACE_PATTERN.match(name):
            raise NetworkChangeError(f"interface name '{name}' is invalid")


def _uses_sudo(host: Host) -> bool:
    return host.ssh_username != "root" and host.sudo_mode == SudoMode.PASSWORDLESS
