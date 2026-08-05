"""Browser security helpers."""

import hmac
import secrets

from fastapi import Request, Response

from nexora.config import Settings

SESSION_COOKIE = "nexora_session"
CSRF_COOKIE = "nexora_csrf"
PREAUTH_CSRF_COOKIE = "nexora_preauth_csrf"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(cookie_token: str | None, form_token: str | None) -> bool:
    if not cookie_token or not form_token:
        return False
    return hmac.compare_digest(cookie_token, form_token)


def set_cookie(
    response: Response,
    name: str,
    value: str,
    settings: Settings,
    *,
    max_age: int,
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


def delete_auth_cookies(response: Response, settings: Settings) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="strict",
            path="/",
        )


def remote_address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"
