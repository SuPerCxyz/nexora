from lxml import etree

from nexora.vms.clone_xml import build_clone_xml

SOURCE = b"""<domain type="kvm">
  <name>source</name><uuid>11111111-1111-1111-1111-111111111111</uuid>
  <metadata><future value="preserve"/></metadata>
  <os><type arch="x86_64">hvm</type><nvram>/pool/source_VARS.fd</nvram></os>
  <devices>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="/pool/source.qcow2"/><target dev="vda" bus="virtio"/>
      <vendor-extension enabled="yes"/>
    </disk>
    <interface type="bridge">
      <mac address="52:54:00:00:00:01"/><source bridge="br0"/>
      <target dev="vnet9"/><model type="virtio"/>
    </interface>
  </devices>
</domain>"""


def test_clone_xml_changes_only_identity_files_and_mac() -> None:
    result = build_clone_xml(
        SOURCE,
        name="clone",
        vm_uuid="22222222-2222-2222-2222-222222222222",
        disk_paths={"/pool/source.qcow2": "/pool/clone.qcow2"},
        nvram_path="/pool/clone_VARS.fd",
        mac_addresses=("52:54:00:aa:bb:cc",),
    )
    root = etree.fromstring(result)
    assert "clone" == root.findtext("name")
    assert "22222222-2222-2222-2222-222222222222" == root.findtext("uuid")
    assert "/pool/clone.qcow2" == root.find("./devices/disk/source").get("file")
    assert "/pool/clone_VARS.fd" == root.findtext("./os/nvram")
    assert "52:54:00:aa:bb:cc" == root.find("./devices/interface/mac").get("address")
    assert root.find("./devices/interface/target") is None
    assert "preserve" == root.find("./metadata/future").get("value")
    assert "yes" == root.find("./devices/disk/vendor-extension").get("enabled")
