"""Session-only administrator account and preference APIs."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexora.auth.passwords import PasswordPolicyError
from nexora.auth.service import (
    AuthenticationFailedError,
    ConcurrentAccountChangeError,
    InvalidUsernameError,
)
from nexora.web.internal.auth import (
    internal_error,
    no_store,
    resolve_internal_identity,
    verify_internal_csrf,
)
from nexora.web.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    delete_auth_cookies,
    set_cookie,
)

router = APIRouter(prefix="/internal", include_in_schema=False)


class AccountUpdateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str | None = Field(default=None, max_length=512)
    confirmation: str | None = Field(default=None, max_length=512)
    session_timeout_minutes: int = Field(ge=5, le=1440)
    global_monospace: bool = False
    density: str = Field(max_length=16)
    language: str = Field(max_length=16)
    timezone: str = Field(min_length=1, max_length=64)


@router.get("/account")
async def internal_account(request: Request) -> JSONResponse:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    identity = resolved.identity
    history = request.app.state.auth_service.login_history()
    payload = {
        "administrator": {
            "username": identity.username,
            "session_timeout_minutes": identity.session_timeout_minutes,
            "global_monospace": identity.global_monospace,
            "density": identity.density,
            "language": identity.language,
            "timezone": identity.timezone,
        },
        "login_history": [
            {
                "occurred_at": attempt.occurred_at.isoformat(),
                "username": attempt.username,
                "remote_address": attempt.remote_address,
                "succeeded": attempt.succeeded,
            }
            for attempt in history
        ],
    }
    return no_store(JSONResponse(payload))


@router.post("/account")
async def internal_account_update(
    request: Request, submitted: AccountUpdateRequest
) -> JSONResponse:
    csrf_error = _write_error(request)
    if csrf_error is not None:
        return csrf_error
    try:
        administrator = request.app.state.auth_service.update_account(
            current_password=submitted.current_password,
            username=submitted.username,
            new_password=submitted.new_password or None,
            confirmation=submitted.confirmation or None,
            session_timeout_minutes=submitted.session_timeout_minutes,
            global_monospace=submitted.global_monospace,
            density=submitted.density,
            language=submitted.language,
            timezone=submitted.timezone,
        )
    except (
        AuthenticationFailedError,
        ConcurrentAccountChangeError,
        InvalidUsernameError,
        PasswordPolicyError,
        ValueError,
    ) as exc:
        return internal_error(422, "account_update_failed", str(exc) or "账户更新失败")
    credentials = request.app.state.session_service.create(administrator.id)
    response = no_store(
        JSONResponse(
            {
                "username": administrator.username,
                "csrf_token": credentials.csrf_token,
                "redirect": "/",
            }
        )
    )
    max_age = max(1, int((credentials.expires_at - datetime.now(UTC)).total_seconds()))
    settings = request.app.state.settings
    set_cookie(response, SESSION_COOKIE, credentials.token, settings, max_age=max_age)
    set_cookie(response, CSRF_COOKIE, credentials.csrf_token, settings, max_age=max_age)
    return response


@router.post("/logout")
async def internal_logout(request: Request) -> JSONResponse:
    csrf_error = _write_error(request)
    if csrf_error is not None:
        return csrf_error
    token = request.cookies.get(SESSION_COOKIE)
    assert token is not None
    request.app.state.session_service.revoke(token)
    response = no_store(JSONResponse({"redirect": "/login"}))
    delete_auth_cookies(response, request.app.state.settings)
    return response


def _write_error(request: Request) -> JSONResponse | None:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return verify_internal_csrf(request)
