"""Deterministic NoCloud configuration documents."""

import json
from dataclasses import dataclass
from hashlib import sha256

from nexora.vms.media_creation_contracts import VmMediaCreateInput


@dataclass(frozen=True)
class CloudInitDocuments:
    user_data: bytes
    meta_data: bytes
    network_config: bytes

    @property
    def digests(self) -> tuple[str, str, str]:
        return (
            sha256(self.user_data).hexdigest(),
            sha256(self.meta_data).hexdigest(),
            sha256(self.network_config).hexdigest(),
        )


def build_cloud_init_documents(create: VmMediaCreateInput) -> CloudInitDocuments | None:
    if create.cloud_username is None:
        return None
    assert create.cloud_hostname is not None
    user: dict[str, object] = {
        "name": create.cloud_username,
        "lock_passwd": create.cloud_password_hash is None,
        "shell": "/bin/bash",
        "sudo": ["ALL=(ALL) NOPASSWD:ALL"],
    }
    if create.cloud_ssh_public_key is not None:
        user["ssh_authorized_keys"] = [create.cloud_ssh_public_key]
    if create.cloud_password_hash is not None:
        user["passwd"] = create.cloud_password_hash
    user_config: dict[str, object] = {
        "hostname": create.cloud_hostname,
        "manage_etc_hosts": True,
        "ssh_pwauth": create.cloud_password_hash is not None,
        "users": [user],
        "chpasswd": {"expire": False},
    }
    meta_config = {
        "instance-id": f"nexora-{create.vm_uuid}",
        "local-hostname": create.cloud_hostname,
    }
    network_config: dict[str, object] = {"version": 2, "ethernets": {}}
    if create.network_mac is not None:
        ethernet: dict[str, object] = {
            "match": {"macaddress": create.network_mac},
        }
        if create.cloud_network_mode == "static":
            addresses = [
                value
                for value in (create.cloud_ipv4_cidr, create.cloud_ipv6_cidr)
                if value is not None
            ]
            routes = []
            if create.cloud_ipv4_gateway is not None:
                routes.append({"to": "0.0.0.0/0", "via": create.cloud_ipv4_gateway})
            if create.cloud_ipv6_gateway is not None:
                routes.append({"to": "::/0", "via": create.cloud_ipv6_gateway})
            ethernet.update(
                {
                    "dhcp4": False,
                    "dhcp6": False,
                    "addresses": addresses,
                    "routes": routes,
                    "nameservers": {"addresses": list(create.cloud_dns_addresses)},
                }
            )
        else:
            ethernet.update({"dhcp4": True, "dhcp6": True})
        network_config["ethernets"] = {"nexora0": ethernet}
    return CloudInitDocuments(
        b"#cloud-config\n" + _json(user_config),
        _json(meta_config),
        _json(network_config),
    )


def cloud_init_seed_name(create: VmMediaCreateInput) -> str | None:
    if create.cloud_username is None:
        return None
    return f"nexora-cloudinit-{create.vm_uuid}.iso"


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
