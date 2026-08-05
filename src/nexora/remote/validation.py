"""SSH target validation."""

import ipaddress
import re

HOSTNAME_PATTERN = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def validate_host(host: str) -> str:
    normalized = host.strip()
    try:
        return str(ipaddress.ip_address(normalized))
    except ValueError:
        if not HOSTNAME_PATTERN.fullmatch(normalized):
            raise ValueError("invalid SSH host") from None
        return normalized.lower()


def validate_port(port: int) -> int:
    if not 1 <= port <= 65_535:
        raise ValueError("invalid SSH port")
    return port


def validate_resource_id(resource_id: str) -> str:
    if not RESOURCE_ID_PATTERN.fullmatch(resource_id):
        raise ValueError("invalid resource identifier")
    return resource_id
