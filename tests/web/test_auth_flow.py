from fastapi.testclient import TestClient
from httpx2 import Response

from nexora.app import create_app
from nexora.config import Settings
from nexora.web.security import CSRF_COOKIE, PREAUTH_CSRF_COOKIE, SESSION_COOKIE


def _initialize(client: TestClient) -> Response:
    page = client.get("/initialize")
    assert 200 == page.status_code
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
    assert "/" == response.headers["location"]
    return response


def test_initialization_is_required_and_creates_session(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/", follow_redirects=False)
        assert 303 == response.status_code
        assert "/initialize" == response.headers["location"]

        initialization = _initialize(client)

        dashboard = client.get("/")
        assert 200 == dashboard.status_code
        assert 'id="nexora-root"' in dashboard.text
        overview = client.get("/internal/overview")
        assert 200 == overview.status_code
        assert 0 == overview.json()["host_total"]
        assert 0 == overview.json()["vm_total"]
        assert client.cookies.get(SESSION_COOKIE)
        assert client.cookies.get(CSRF_COOKIE)
        assert "default-src 'self'" in dashboard.headers["content-security-policy"]
        cookies = "\n".join(initialization.headers.get_list("set-cookie"))
        assert "HttpOnly" in cookies
        assert "SameSite=strict" in cookies


def test_initialization_rejects_missing_csrf(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/initialize",
            data={
                "username": "admin",
                "password": "a-valid-password",
                "confirmation": "a-valid-password",
            },
        )

    assert 403 == response.status_code
    assert "请求已失效" in response.text


def test_logout_and_login_round_trip(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        csrf_token = client.cookies.get(CSRF_COOKIE)
        assert csrf_token

        logout = client.post(
            "/internal/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert 200 == logout.status_code
        assert client.cookies.get(SESSION_COOKIE) is None

        login_page = client.get("/login")
        preauth = client.cookies.get(PREAUTH_CSRF_COOKIE)
        assert 200 == login_page.status_code
        assert preauth
        login = client.post(
            "/login",
            data={
                "csrf_token": preauth,
                "username": "admin",
                "password": "a-valid-password",
            },
            follow_redirects=False,
        )
        assert 303 == login.status_code
        assert client.cookies.get(SESSION_COOKIE)
        history = client.get("/settings/account")
        history_api = client.get("/internal/account")
        assert 'id="nexora-root"' in history.text
        assert history_api.json()["login_history"][0]["succeeded"]


def test_logout_rejects_missing_csrf_without_clearing_session(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        session_token = client.cookies.get(SESSION_COOKIE)

        response = client.post("/internal/logout")

        assert 403 == response.status_code
        assert session_token == client.cookies.get(SESSION_COOKIE)
        assert 200 == client.get("/").status_code


def test_internal_logout_clears_authenticated_session(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        response = client.post(
            "/internal/logout",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )

        assert 200 == response.status_code
        assert "/login" == response.json()["redirect"]
        assert client.cookies.get(SESSION_COOKIE) is None
        assert 303 == client.get("/", follow_redirects=False).status_code


def test_account_change_rotates_session(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        _initialize(client)
        old_session = client.cookies.get(SESSION_COOKIE)
        csrf_token = client.cookies.get(CSRF_COOKIE)
        assert old_session and csrf_token

        response = client.post(
            "/internal/account",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "username": "operator",
                "current_password": "a-valid-password",
                "new_password": "a-new-valid-password",
                "confirmation": "a-new-valid-password",
                "session_timeout_minutes": 60,
                "global_monospace": True,
                "density": "compact",
                "language": "en",
                "timezone": "UTC",
            },
        )

        assert 200 == response.status_code
        assert "/" == response.json()["redirect"]
        assert old_session != client.cookies.get(SESSION_COOKIE)
        dashboard = client.get("/")
        assert 'id="nexora-root"' in dashboard.text
        internal_session = client.get("/internal/session")
        administrator = internal_session.json()["administrator"]
        assert "operator" == administrator["username"]
        assert "en" == administrator["language"]
        assert administrator["global_monospace"] is True
        assert "compact" == administrator["density"]
