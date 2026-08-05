"""Safe libvirt dir and netfs storage pool XML generation."""

from uuid import UUID

from lxml import etree

from nexora.storage.contracts import StoragePoolCreateInput
from nexora.xml.document import LibvirtXmlDocument

FS_NAMESPACE = "http://libvirt.org/schemas/storagepool/fs/1.0"


def build_pool_xml(create: StoragePoolCreateInput, pool_uuid: str) -> bytes:
    create.validate()
    canonical_uuid = str(UUID(pool_uuid))
    namespace = {"fs": FS_NAMESPACE} if create.mount_options else None
    root = etree.Element("pool", type=create.pool_type, nsmap=namespace)
    etree.SubElement(root, "name").text = create.name
    etree.SubElement(root, "uuid").text = canonical_uuid
    if create.pool_type == "netfs":
        assert create.source_host is not None
        assert create.source_path is not None
        assert create.nfs_version is not None
        source = etree.SubElement(root, "source")
        etree.SubElement(source, "host", name=create.source_host)
        etree.SubElement(source, "dir", path=create.source_path)
        etree.SubElement(source, "format", type="nfs")
        etree.SubElement(source, "protocol", ver=create.nfs_version)
    target = etree.SubElement(root, "target")
    etree.SubElement(target, "path").text = create.target_path
    if create.mount_options:
        mount_opts = etree.SubElement(root, f"{{{FS_NAMESPACE}}}mount_opts")
        for option in create.mount_options:
            etree.SubElement(mount_opts, f"{{{FS_NAMESPACE}}}option", name=option)
    content = etree.tostring(root, encoding="utf-8")
    document = LibvirtXmlDocument.parse(content, expected_root="pool")
    return document.serialize()
