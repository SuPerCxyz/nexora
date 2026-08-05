from fastapi.testclient import TestClient

from nexora.app import create_app
from nexora.config import Settings


def test_liveness(settings: Settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/live")

    assert 200 == response.status_code
    assert {"status": "ok"} == response.json()


def test_readiness_follows_lifespan(settings: Settings) -> None:
    app = create_app(settings)
    assert app.state.ready is False

    with TestClient(app) as client:
        response = client.get("/ready")
        assert 200 == response.status_code
        assert {"status": "ok"} == response.json()

    assert app.state.ready is False


def test_openapi_is_not_exposed(settings: Settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert 404 == response.status_code


def test_untrusted_host_is_rejected(settings: Settings) -> None:
    app = create_app(settings)

    with TestClient(app, base_url="http://untrusted.example") as client:
        response = client.get("/live")

    assert 400 == response.status_code
