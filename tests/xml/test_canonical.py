from nexora.xml import LibvirtXmlDocument
from nexora.xml.diff import xml_diff


def test_fingerprint_ignores_indentation_and_attribute_order() -> None:
    first = LibvirtXmlDocument.parse(b'<domain type="kvm" id="4">\n  <name>guest</name>\n</domain>')
    second = LibvirtXmlDocument.parse(b'<domain id="4" type="kvm"><name>guest</name></domain>')

    assert first.fingerprint() == second.fingerprint()


def test_fingerprint_is_versioned_and_tracks_unknown_content() -> None:
    first = LibvirtXmlDocument.parse(
        b'<domain xmlns:x="urn:vendor"><x:setting enabled="yes"/></domain>'
    )
    second = LibvirtXmlDocument.parse(
        b'<domain xmlns:x="urn:vendor"><x:setting enabled="no"/></domain>'
    )

    assert "nexora-libvirt-c14n2-v1" == first.fingerprint().algorithm
    assert first.fingerprint().digest != second.fingerprint().digest


def test_xml_space_preserve_keeps_significant_whitespace() -> None:
    first = LibvirtXmlDocument.parse(
        b'<domain><metadata xml:space="preserve">  <value/>  </metadata></domain>'
    )
    second = LibvirtXmlDocument.parse(
        b'<domain><metadata xml:space="preserve"><value/></metadata></domain>'
    )

    assert first.fingerprint().digest != second.fingerprint().digest


def test_diff_names_current_and_proposed_documents() -> None:
    current = LibvirtXmlDocument.parse(b"<domain><name>old</name></domain>")
    proposed = LibvirtXmlDocument.parse(b"<domain><name>new</name></domain>")

    rendered = xml_diff(current, proposed)

    assert "--- current.xml" in rendered
    assert "+++ proposed.xml" in rendered
    assert "-  <name>old</name>" in rendered
    assert "+  <name>new</name>" in rendered
