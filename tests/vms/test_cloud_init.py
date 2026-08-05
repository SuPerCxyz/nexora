from dataclasses import replace

import pytest
from lxml import etree

from nexora.vms.cloud_init import (
    build_cloud_init_documents,
    cloud_init_seed_name,
)
from nexora.vms.cloud_password import hash_guest_password
from nexora.vms.creation_xml import build_import_domain_xml
from nexora.vms.media_creation_contracts import VmMediaCreateInput

VM_UUID = "22222222-2222-2222-2222-222222222222"
SSH_KEY = "ssh-ed25519 " + "A" * 68 + " integration@test"


def test_cloud_init_documents_are_deterministic_and_do_not_enable_password() -> None:
    create = _input()
    documents = build_cloud_init_documents(create)
    assert documents is not None
    assert b"#cloud-config" in documents.user_data
    assert b'"ssh_pwauth":false' in documents.user_data
    assert SSH_KEY.encode() in documents.user_data
    assert b'"dhcp4":true' in documents.network_config
    assert create.network_mac.encode() in documents.network_config  # type: ignore[union-attr]
    assert documents.digests == build_cloud_init_documents(create).digests  # type: ignore[union-attr]
    assert f"nexora-cloudinit-{VM_UUID}.iso" == cloud_init_seed_name(create)


def test_cloud_init_requires_selected_network_and_valid_public_key() -> None:
    create = _input()
    with pytest.raises(ValueError, match="selected network"):
        replace(
            create,
            network_kind="none",
            network_resource_id=None,
            network_native_id=None,
            network_generation=None,
            network_hash=None,
            network_name=None,
            network_mac=None,
        ).validate()
    with pytest.raises(ValueError, match="public key"):
        replace(create, cloud_ssh_public_key="not-a-key").validate()


def test_cloud_init_xml_has_planned_mac_and_readonly_seed_cdrom() -> None:
    create = _input()
    seed = f"/images/{cloud_init_seed_name(create)}"
    content = build_import_domain_xml(
        create,
        architecture="x86_64",
        disk_path="/images/system.qcow2",
        disk_format="qcow2",
        cloud_init_path=seed,
    )
    root = etree.fromstring(content)
    assert create.network_mac == root.find("./devices/interface/mac").get("address")
    cdroms = root.xpath("./devices/disk[target[@dev='sdb']]")
    assert 1 == len(cdroms)
    cdrom = cdroms[0]
    assert seed == cdrom.find("source").get("file")
    assert cdrom.find("readonly") is not None


def test_cloud_init_password_is_hashed_and_static_ipv4_is_structured() -> None:
    password = "a-long-guest-password"
    digest = hash_guest_password(password, password)
    assert digest is not None and digest.startswith("$6$")
    create = replace(
        _input(),
        cloud_password_hash=digest,
        cloud_network_mode="static",
        cloud_ipv4_cidr="192.0.2.10/24",
        cloud_ipv4_gateway="192.0.2.1",
        cloud_dns_addresses=("1.1.1.1", "2001:4860:4860::8888"),
    )
    create.validate()
    documents = build_cloud_init_documents(create)
    assert documents is not None
    assert password.encode() not in documents.user_data
    assert digest.encode() in documents.user_data
    assert b'"ssh_pwauth":true' in documents.user_data
    assert b'"addresses":["192.0.2.10/24"]' in documents.network_config
    assert b'"to":"0.0.0.0/0"' in documents.network_config
    assert b'"dhcp4":false' in documents.network_config


def test_cloud_init_static_ipv4_rejects_gateway_outside_subnet() -> None:
    with pytest.raises(ValueError, match="outside"):
        replace(
            _input(),
            cloud_network_mode="static",
            cloud_ipv4_cidr="192.0.2.10/24",
            cloud_ipv4_gateway="198.51.100.1",
            cloud_dns_addresses=("1.1.1.1",),
        ).validate()


def test_cloud_init_static_ipv6_and_dual_stack_are_structured() -> None:
    create = replace(
        _input(),
        cloud_network_mode="static",
        cloud_ipv4_cidr="192.0.2.10/24",
        cloud_ipv4_gateway="192.0.2.1",
        cloud_ipv6_cidr="2001:db8::10/64",
        cloud_ipv6_gateway="2001:db8::1",
        cloud_dns_addresses=("1.1.1.1", "2001:4860:4860::8888"),
    )
    create.validate()
    documents = build_cloud_init_documents(create)
    assert documents is not None
    assert b'"2001:db8::10/64"' in documents.network_config
    assert b'"to":"::/0"' in documents.network_config
    assert b'"via":"2001:db8::1"' in documents.network_config


def test_cloud_init_static_ipv6_rejects_unsafe_or_cross_subnet_gateway() -> None:
    with pytest.raises(ValueError, match="outside"):
        replace(
            _input(),
            cloud_network_mode="static",
            cloud_ipv4_cidr=None,
            cloud_ipv4_gateway=None,
            cloud_ipv6_cidr="2001:db8::10/64",
            cloud_ipv6_gateway="2001:db9::1",
            cloud_dns_addresses=("2001:4860:4860::8888",),
        ).validate()


def _input() -> VmMediaCreateInput:
    create = VmMediaCreateInput(
        media_item_id="media-1",
        media_sha256="a" * 64,
        media_format="qcow2",
        host_id="host-1",
        pool_resource_id="pool-1",
        pool_uuid="11111111-1111-1111-1111-111111111111",
        pool_generation=1,
        pool_hash="b" * 64,
        target_file_name="system.qcow2",
        name="cloud-vm",
        memory_mib=2048,
        vcpus=2,
        vm_uuid=VM_UUID,
        network_kind="network",
        network_resource_id="network-1",
        network_native_id="33333333-3333-3333-3333-333333333333",
        network_generation=1,
        network_hash="c" * 64,
        network_name="default",
        network_mac="52:54:00:12:34:56",
        cloud_hostname="cloud-vm.example.test",
        cloud_username="nexora",
        cloud_ssh_public_key=SSH_KEY,
        cloud_network_mode="dhcp",
    )
    create.validate()
    return create
