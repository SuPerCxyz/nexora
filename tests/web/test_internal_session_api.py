from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE


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
    )
    assert 200 == response.status_code


def test_internal_session_requires_authentication(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/internal/session")

    assert 401 == response.status_code
    assert {
        "code": "authentication_required",
        "message": "管理员会话已失效",
        "field_errors": {},
        "conflict": None,
        "task_id": None,
    } == response.json()
    assert "no-store" == response.headers["cache-control"]


def test_internal_session_returns_preferences_and_csrf(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        csrf_token = client.cookies.get(CSRF_COOKIE)
        response = client.get("/internal/session")

    assert 200 == response.status_code
    assert {
        "administrator": {
            "username": "admin",
            "global_monospace": False,
            "density": "comfortable",
            "language": "zh-CN",
            "timezone": "Asia/Shanghai",
        },
        "csrf_token": csrf_token,
        "features": {"react_preview": True, "react_core_pages": True},
    } == response.json()
    assert "no-store" == response.headers["cache-control"]
    assert "no-cache" == response.headers["pragma"]
