"""Administrator initialization and login routes."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse
from starlette.datastructures import FormData
from starlette.responses import Response

from nexora.auth.passwords import PasswordPolicyError
from nexora.auth.service import (
    AlreadyInitializedError,
    AuthService,
    InvalidUsernameError,
)
from nexora.auth.sessions import SessionService
from nexora.config import Settings
from nexora.web.frontend import render_react_shell
from nexora.web.security import (
    CSRF_COOKIE,
    PREAUTH_CSRF_COOKIE,
    SESSION_COOKIE,
    csrf_matches,
    new_csrf_token,
    remote_address,
    set_cookie,
)

router = APIRouter(include_in_schema=False)


def _services(request: Request) -> tuple[AuthService, SessionService, Settings]:
    return (
        request.app.state.auth_service,
        request.app.state.session_service,
        request.app.state.settings,
    )


def _field(form: FormData, name: str) -> str:
    value = form.get(name, "")
    return value if isinstance(value, str) else ""


def _auth_page(
    request: Request,
    *,
    mode: str,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> Response:
    csrf_token = request.cookies.get(PREAUTH_CSRF_COOKIE) or new_csrf_token()
    response = render_react_shell(
        request,
        auth_mode=mode,
        auth_error=error,
        auth_csrf=csrf_token,
        status_code=status_code,
    )
    settings: Settings = request.app.state.settings
    set_cookie(response, PREAUTH_CSRF_COOKIE, csrf_token, settings, max_age=600)
    return response


@router.get("/initialize")
async def initialize_page(request: Request) -> Response:
    auth_service, _, _ = _services(request)
    if auth_service.is_initialized():
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return _auth_page(request, mode="initialize")


@router.post("/initialize")
async def initialize_submit(request: Request) -> Response:
    auth_service, session_service, settings = _services(request)
    if auth_service.is_initialized():
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not csrf_matches(request.cookies.get(PREAUTH_CSRF_COOKIE), _field(form, "csrf_token")):
        return _auth_page(request, mode="initialize", error="请求已失效，请重试", status_code=403)
    try:
        administrator = auth_service.initialize(
            _field(form, "username"),
            _field(form, "password"),
            _field(form, "confirmation"),
        )
    except (AlreadyInitializedError, InvalidUsernameError, PasswordPolicyError) as exc:
        message = str(exc) or "无法创建管理员"
        return _auth_page(request, mode="initialize", error=message, status_code=422)
    credentials = session_service.create(administrator.id)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    max_age = max(1, int((credentials.expires_at - datetime.now(UTC)).total_seconds()))
    set_cookie(response, SESSION_COOKIE, credentials.token, settings, max_age=max_age)
    set_cookie(response, CSRF_COOKIE, credentials.csrf_token, settings, max_age=max_age)
    response.delete_cookie(PREAUTH_CSRF_COOKIE, path="/")
    return response


@router.get("/login")
async def login_page(request: Request) -> Response:
    auth_service, session_service, _ = _services(request)
    if not auth_service.is_initialized():
        return RedirectResponse("/initialize", status_code=status.HTTP_303_SEE_OTHER)
    if session_service.resolve(request.cookies.get(SESSION_COOKIE)) is not None:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return _auth_page(request, mode="login")


@router.post("/login")
async def login_submit(request: Request) -> Response:
    auth_service, session_service, settings = _services(request)
    if not auth_service.is_initialized():
        return RedirectResponse("/initialize", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    if not csrf_matches(request.cookies.get(PREAUTH_CSRF_COOKIE), _field(form, "csrf_token")):
        return _auth_page(request, mode="login", error="请求已失效，请重试", status_code=403)
    authenticated = auth_service.authenticate(
        _field(form, "username"),
        _field(form, "password"),
        remote_address(request),
    )
    if not authenticated:
        return _auth_page(
            request,
            mode="login",
            error="用户名或密码不正确",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    credentials = session_service.create(1)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    max_age = max(1, int((credentials.expires_at - datetime.now(UTC)).total_seconds()))
    set_cookie(response, SESSION_COOKIE, credentials.token, settings, max_age=max_age)
    set_cookie(response, CSRF_COOKIE, credentials.csrf_token, settings, max_age=max_age)
    response.delete_cookie(PREAUTH_CSRF_COOKIE, path="/")
    return response
