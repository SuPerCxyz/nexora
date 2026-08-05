from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings
from nexora.web.security import PREAUTH_CSRF_COOKIE


def _initialize(client: TestClient) -> None:
    client.get("/initialize")
    token = client.cookies.get(PREAUTH_CSRF_COOKIE)
    assert token
    response = client.post(
        "/initialize",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "a-valid-password",
            "confirmation": "a-valid-password",
        },
    )
    assert 200 == response.status_code


def test_authenticated_navigation_routes_are_available(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)

        for path in ("/", "/hosts", "/vms", "/storage", "/networks", "/tasks", "/audit"):
            response = client.get(path)
            assert 200 == response.status_code
            assert "Nexora" in response.text


def test_section_placeholder_requires_authentication(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/hosts", follow_redirects=False)

    assert 303 == response.status_code
    assert "/initialize" == response.headers["location"]
