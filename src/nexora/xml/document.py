"""Safe, preservation-oriented libvirt XML documents."""

import copy
from dataclasses import dataclass
from hashlib import sha256

from lxml import etree

from nexora.xml.errors import XmlSafetyError, XmlStructureError

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
HASH_ALGORITHM = "nexora-libvirt-c14n2-v1"


@dataclass(frozen=True)
class XmlLimits:
    max_bytes: int = 10 * 1024 * 1024
    max_depth: int = 128
    max_nodes: int = 100_000


@dataclass(frozen=True)
class XmlFingerprint:
    algorithm: str
    digest: str


class LibvirtXmlDocument:
    """Own one parsed tree and preserve unmodified nodes during local edits."""

    def __init__(self, tree: etree._ElementTree, limits: XmlLimits) -> None:
        self.tree = tree
        self.limits = limits

    @classmethod
    def parse(
        cls,
        source: bytes,
        *,
        expected_root: str | None = None,
        limits: XmlLimits | None = None,
    ) -> "LibvirtXmlDocument":
        active_limits = limits or XmlLimits()
        if len(source) > active_limits.max_bytes:
            raise XmlSafetyError("XML exceeds byte limit")
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
            remove_comments=False,
            remove_pis=False,
            strip_cdata=False,
        )
        try:
            root = etree.fromstring(source, parser=parser)
        except etree.XMLSyntaxError as exc:
            raise XmlSafetyError("XML is not safely parseable") from exc
        tree = root.getroottree()
        if tree.docinfo.internalDTD is not None or tree.docinfo.externalDTD is not None:
            raise XmlSafetyError("DOCTYPE is not permitted")
        _enforce_tree_limits(root, active_limits)
        if expected_root is not None and etree.QName(root).localname != expected_root:
            raise XmlStructureError(f"expected {expected_root} root element")
        return cls(tree, active_limits)

    @property
    def root(self) -> etree._Element:
        return self.tree.getroot()

    def serialize(self) -> bytes:
        return etree.tostring(
            self.tree,
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=False,
        )

    def canonical_bytes(self) -> bytes:
        normalized = copy.deepcopy(self.root)
        _remove_indentation(normalized, preserve=False)
        return etree.tostring(normalized, method="c14n2", with_comments=True)

    def fingerprint(self) -> XmlFingerprint:
        payload = HASH_ALGORITHM.encode() + b"\0" + self.canonical_bytes()
        return XmlFingerprint(HASH_ALGORITHM, sha256(payload).hexdigest())


def _enforce_tree_limits(root: etree._Element, limits: XmlLimits) -> None:
    count = 0
    stack: list[tuple[etree._Element, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > limits.max_nodes:
            raise XmlSafetyError("XML exceeds node limit")
        if depth > limits.max_depth:
            raise XmlSafetyError("XML exceeds depth limit")
        stack.extend((child, depth + 1) for child in element if isinstance(child.tag, str))


def _remove_indentation(element: etree._Element, *, preserve: bool) -> None:
    mode = element.get(XML_SPACE)
    if mode == "preserve":
        preserve = True
    elif mode == "default":
        preserve = False
    children = [child for child in element if isinstance(child.tag, str)]
    if not preserve and children and element.text is not None and not element.text.strip():
        element.text = None
    for child in children:
        _remove_indentation(child, preserve=preserve)
        if not preserve and child.tail is not None and not child.tail.strip():
            child.tail = None
