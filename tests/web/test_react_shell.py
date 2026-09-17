import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings
from nexora.web import frontend
from nexora.web.frontend import FrontendAssetError, load_frontend_assets
from nexora.web.security import PREAUTH_CSRF_COOKIE


def _initialize(client: TestClient) -> None:
    client.get("/initialize")
    csrf_token = client.cookies.get(PREAUTH_CSRF_COOKIE)
    assert csrf_token
    response = client.post(
        "/initialize",
        data={
            "csrf_token": csrf_token,
            "username": "admin",
            "password": "a-valid-password",
            "confirmation": "a-valid-password",
        },
        follow_redirects=False,
    )
    assert 303 == response.status_code


def _csp_nonce(policy: str) -> str:
    match = re.search(r"script-src 'self' 'nonce-([^']+)'", policy)
    assert match
    return match.group(1)


def test_react_shell_requires_authentication(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/ui-preview", follow_redirects=False)

    assert 303 == response.status_code
    assert "/initialize" == response.headers["location"]


def test_react_shell_loads_manifest_assets_and_nonce(settings: Settings) -> None:
    manifest = json.loads((frontend.APP_ASSET_ROOT / ".vite/manifest.json").read_text())
    entry = manifest[frontend.ENTRY_NAME]
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        response = client.get("/ui-preview")

    nonce = _csp_nonce(response.headers["content-security-policy"])
    assert 200 == response.status_code
    assert 'id="nexora-root"' in response.text
    assert f'content="{nonce}"' in response.text
    assert f"/static/app/{entry['file']}" in response.text
    assert all(f"/static/app/{item}" in response.text for item in entry["css"])
    assert "no-store" == response.headers["cache-control"]


def test_react_shell_supports_deep_refresh(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        response = client.get("/ui-preview/hosts/example")

    assert 200 == response.status_code
    assert 'id="nexora-root"' in response.text


def test_react_shell_owns_core_read_only_urls(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        for path in ("/", "/hosts", "/vms"):
            response = client.get(path)
            assert 200 == response.status_code
            assert 'id="nexora-root"' in response.text

        assert "创建本地管理员" not in response.text


def test_react_shell_owns_uuid_resource_details(settings: Settings) -> None:
    host_id = "11111111-1111-1111-1111-111111111111"
    vm_id = "22222222-2222-2222-2222-222222222222"
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        host = client.get(f"/hosts/{host_id}")
        managed_host = client.get(f"/manage/hosts/{host_id}")
        removed_host = client.get(f"/hosts/{host_id}/remove")
        vm = client.get(f"/hosts/{host_id}/vms/{vm_id}")
        config = client.get(f"/hosts/{host_id}/vms/{vm_id}/config")
        legacy_config = client.get(f"/manage/hosts/{host_id}/vms/{vm_id}")
        legacy_config_explicit = client.get(f"/manage/hosts/{host_id}/vms/{vm_id}/config")

    assert 200 == host.status_code
    assert 'id="nexora-root"' in host.text
    assert 'id="nexora-root"' in managed_host.text
    assert 'id="nexora-root"' in removed_host.text
    assert 200 == vm.status_code
    assert 'id="nexora-root"' in vm.text
    assert 200 == config.status_code
    assert 'id="nexora-root"' in config.text
    assert 200 == legacy_config.status_code
    assert 'id="nexora-root"' in legacy_config.text
    assert 200 == legacy_config_explicit.status_code
    assert 'id="nexora-root"' in legacy_config_explicit.text


def test_react_shell_fails_closed_without_assets(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(frontend, "APP_ASSET_ROOT", tmp_path)
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        response = client.get("/ui-preview")

    assert 503 == response.status_code
    assert "Frontend assets unavailable" == response.text
    assert "no-store" == response.headers["cache-control"]


def test_manifest_rejects_unsafe_asset_path(tmp_path: Path) -> None:
    manifest_dir = tmp_path / ".vite"
    manifest_dir.mkdir()
    manifest_dir.joinpath("manifest.json").write_text(
        json.dumps({frontend.ENTRY_NAME: {"file": "../escape.js", "isEntry": True}})
    )

    with pytest.raises(FrontendAssetError, match="unsafe"):
        load_frontend_assets(tmp_path)
