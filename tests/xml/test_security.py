from pathlib import Path

import pytest

from nexora.xml import LibvirtXmlDocument, XmlLimits, XmlSafetyError, XmlStructureError


def test_rejects_doctype_and_does_not_read_external_entity(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("must-not-be-read")
    source = (
        f'<!DOCTYPE domain [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]>'
        "<domain><name>&xxe;</name></domain>"
    ).encode()

    with pytest.raises(XmlSafetyError, match="DOCTYPE"):
        LibvirtXmlDocument.parse(source, expected_root="domain")


def test_xinclude_is_preserved_but_never_expanded(tmp_path: Path) -> None:
    target = tmp_path / "included.xml"
    target.write_text("<secret>must-not-appear</secret>")
    source = (
        '<domain xmlns:xi="http://www.w3.org/2001/XInclude">'
        f'<xi:include href="{target.as_uri()}"/>'
        "</domain>"
    ).encode()

    document = LibvirtXmlDocument.parse(source, expected_root="domain")

    rendered = document.serialize()
    assert b"xi:include" in rendered
    assert b"must-not-appear" not in rendered


def test_enforces_byte_depth_and_node_limits() -> None:
    with pytest.raises(XmlSafetyError, match="byte limit"):
        LibvirtXmlDocument.parse(b"<domain/>", limits=XmlLimits(max_bytes=4))

    with pytest.raises(XmlSafetyError, match="depth limit"):
        LibvirtXmlDocument.parse(
            b"<domain><a><b/></a></domain>",
            limits=XmlLimits(max_depth=2),
        )

    with pytest.raises(XmlSafetyError, match="node limit"):
        LibvirtXmlDocument.parse(
            b"<domain><a/><b/></domain>",
            limits=XmlLimits(max_nodes=2),
        )


def test_expected_root_is_required_when_requested() -> None:
    with pytest.raises(XmlStructureError, match="domain"):
        LibvirtXmlDocument.parse(b"<network/>", expected_root="domain")
