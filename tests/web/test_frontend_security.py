import re
from pathlib import Path

from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings


def _nonce(response_header: str) -> str:
    match = re.search(r"script-src 'self' 'nonce-([^']+)'", response_header)
    assert match
    return match.group(1)


def test_csp_uses_a_unique_nonce_per_response(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        first = client.get("/live")
        second = client.get("/live")

    first_policy = first.headers["content-security-policy"]
    second_policy = second.headers["content-security-policy"]
    assert _nonce(first_policy) != _nonce(second_policy)
    assert "script-src 'self' 'unsafe-inline'" not in first_policy
    assert "style-src-elem 'self' 'nonce-" in first_policy
    assert "style-src-attr 'unsafe-inline'" in first_policy
    assert "https:" not in first_policy


def test_react_frontend_does_not_parse_legacy_html_previews() -> None:
    source = Path("frontend/src")
    matches = [
        path
        for path in source.rglob("*")
        if path.suffix in {".ts", ".tsx"} and "DOMParser" in path.read_text(encoding="utf-8")
    ]
    assert [] == matches
