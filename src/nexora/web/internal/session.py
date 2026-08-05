"""Authenticated React bootstrap Session endpoint."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from nexora.web.internal.auth import InternalIdentity, no_store, resolve_internal_identity
from nexora.web.internal.contracts import AdministratorPreferences, InternalSession

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/session")
async def internal_session(request: Request) -> JSONResponse:
    resolved = resolve_internal_identity(request)
    if isinstance(resolved, JSONResponse):
        return resolved
    return _session_response(resolved)


def _session_response(resolved: InternalIdentity) -> JSONResponse:
    identity = resolved.identity
    payload = InternalSession(
        administrator=AdministratorPreferences(
            username=identity.username,
            global_monospace=identity.global_monospace,
            density=identity.density,
            language=identity.language,
            timezone=identity.timezone,
        ),
        csrf_token=resolved.csrf_token,
        features={"react_preview": True, "react_core_pages": True},
    )
    return no_store(JSONResponse(payload.model_dump()))
