from uuid import UUID

from lxml import etree

from nexora.storage.contracts import StoragePoolCreateInput
from nexora.storage.xml import FS_NAMESPACE, build_pool_xml
from nexora.xml.document import LibvirtXmlDocument


def test_build_dir_pool_xml() -> None:
    pool_uuid = "c53521f4-838b-4f01-a6d1-a0a9b6294561"
    create = StoragePoolCreateInput(
        host_id="host-1",
        name="images",
        pool_type="dir",
        target_path="/var/lib/libvirt/images",
    )

    document = LibvirtXmlDocument.parse(build_pool_xml(create, pool_uuid), expected_root="pool")

    assert "dir" == document.root.get("type")
    assert "images" == document.root.findtext("name")
    assert str(UUID(pool_uuid)) == document.root.findtext("uuid")
    assert "/var/lib/libvirt/images" == document.root.findtext("target/path")
    assert document.root.find("source") is None


def test_build_netfs_pool_xml_with_namespaced_mount_options() -> None:
    create = StoragePoolCreateInput(
        host_id="host-1",
        name="nfs-vms",
        pool_type="netfs",
        target_path="/var/lib/libvirt/nexora-nfs",
        source_host="nfs.example.test",
        source_path="/exports/vms",
        nfs_version="4",
        mount_options=("rw", "hard", "timeo=600"),
    )

    root = etree.fromstring(build_pool_xml(create, "693c22b5-284b-452b-8574-c285aa18bcc3"))

    assert "nfs.example.test" == root.find("source/host").get("name")
    assert "/exports/vms" == root.find("source/dir").get("path")
    assert "4" == root.find("source/protocol").get("ver")
    options = root.findall(f"{{{FS_NAMESPACE}}}mount_opts/{{{FS_NAMESPACE}}}option")
    assert ["rw", "hard", "timeo=600"] == [item.get("name") for item in options]
