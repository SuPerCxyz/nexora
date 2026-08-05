"""Session and CSRF guards for internal frontend endpoints."""

from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

from nexora.auth.sessions import SessionIdentity, SessionService
from nexora.web.internal.contracts import InternalError
from nexora.web.security import CSRF_COOKIE, SESSION_COOKIE


@dataclass(frozen=True)
class InternalIdentity:
    identity: SessionIdentity
    csrf_token: str


def resolve_internal_identity(request: Request) -> InternalIdentity | JSONResponse:
    session_service: SessionService = request.app.state.session_service
    identity = session_service.resolve(request.cookies.get(SESSION_COOKIE))
    csrf_token = request.cookies.get(CSRF_COOKIE)
    if identity is None or csrf_token is None:
        return internal_error(401, "authentication_required", "管理员会话已失效")
    return InternalIdentity(identity, csrf_token)


def verify_internal_csrf(request: Request) -> JSONResponse | None:
    token = request.cookies.get(SESSION_COOKIE)
    submitted = request.headers.get("X-CSRF-Token")
    service: SessionService = request.app.state.session_service
    if token is None or submitted is None or not service.verify_csrf(token, submitted):
        return internal_error(403, "csrf_validation_failed", "CSRF validation failed")
    return None


def internal_error(status_code: int, code: str, message: str) -> JSONResponse:
    payload = InternalError(code=code, message=message)
    return no_store(JSONResponse(payload.model_dump(), status_code=status_code))


def no_store(response: JSONResponse) -> JSONResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response
