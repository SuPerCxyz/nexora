"""Human-reviewable XML differences."""

from difflib import unified_diff

from lxml import etree

from nexora.xml.document import LibvirtXmlDocument


def xml_diff(
    before: LibvirtXmlDocument,
    after: LibvirtXmlDocument,
    *,
    before_name: str = "current.xml",
    after_name: str = "proposed.xml",
) -> str:
    before_lines = _pretty_lines(before)
    after_lines = _pretty_lines(after)
    return "".join(
        unified_diff(
            before_lines,
            after_lines,
            fromfile=before_name,
            tofile=after_name,
        )
    )


def _pretty_lines(document: LibvirtXmlDocument) -> list[str]:
    rendered = etree.tostring(document.root, encoding="unicode", pretty_print=True)
    return rendered.splitlines(keepends=True)
