"""Liveness and readiness endpoints."""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

router = APIRouter(include_in_schema=False)


class HealthResponse(BaseModel):
    """Minimal health response without implementation details."""

    status: Literal["ok", "not_ready"]


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Report whether the ASGI process can serve requests."""

    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def readiness(request: Request, response: Response) -> HealthResponse:
    """Report whether application startup completed."""

    if not request.app.state.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="not_ready")
    return HealthResponse(status="ok")
