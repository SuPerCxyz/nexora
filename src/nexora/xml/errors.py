"""Safe XML processing errors."""


class XmlSafetyError(ValueError):
    """Input violates an XML parser resource or external-reference boundary."""


class XmlStructureError(ValueError):
    """Input is well-formed but not a supported libvirt document shape."""


class CpuTopologyError(ValueError):
    """Requested CPU topology is internally inconsistent."""
