from datetime import UTC, datetime

from fastapi.testclient import TestClient
from web.test_vms import _initialize

from nexora.app import create_app
from nexora.audit.models import RemoteCommandLog
from nexora.config import Settings


def test_audit_page_is_authenticated_filtered_and_escaped(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert 303 == client.get("/audit", follow_redirects=False).status_code
        _initialize(client)
        with client.app.state.database.session() as session:
            session.add(
                RemoteCommandLog(
                    operation_id="11111111-1111-1111-1111-111111111111",
                    host_id="removed-host",
                    command_summary="<script>alert(1)</script>",
                    exit_code=1,
                    timed_out=False,
                    cancelled=False,
                    stdout_summary="",
                    stderr_summary="safe error",
                    occurred_at=datetime.now(UTC),
                )
            )

        response = client.get("/audit?outcome=failed")
        api = client.get("/internal/audit?outcome=failed")

        assert 200 == response.status_code
        assert 'id="nexora-root"' in response.text
        assert "<script>alert(1)</script>" not in response.text
        assert "已移除节点" == api.json()["items"][0]["host_name"]
        assert "<script>alert(1)</script>" == api.json()["items"][0]["command_summary"]
        assert 422 == client.get("/internal/audit?outcome=invalid").status_code
