"""Authenticated React application shell."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.responses import Response

from nexora.auth.service import AuthService
from nexora.auth.sessions import SessionService
from nexora.web.rendering import PROJECT_ROOT, templates
from nexora.web.security import SESSION_COOKIE

router = APIRouter(include_in_schema=False)
APP_ASSET_ROOT = PROJECT_ROOT / "static" / "app"
ENTRY_NAME = "src/main.tsx"


class FrontendAssetError(RuntimeError):
    """The production frontend asset set is incomplete or invalid."""


@dataclass(frozen=True)
class FrontendAssets:
    script: str
    styles: tuple[str, ...]
    preloads: tuple[str, ...]


def load_frontend_assets(asset_root: Path | None = None) -> FrontendAssets:
    asset_root = asset_root or APP_ASSET_ROOT
    manifest = _read_manifest(asset_root / ".vite" / "manifest.json")
    entry = manifest.get(ENTRY_NAME)
    if not isinstance(entry, dict) or entry.get("isEntry") is not True:
        raise FrontendAssetError("Frontend entry is missing")
    script = _asset_url(asset_root, entry.get("file"))
    styles = tuple(_asset_url(asset_root, path) for path in _string_list(entry.get("css", [])))
    preloads = tuple(
        _asset_url(asset_root, _manifest_chunk(manifest, name).get("file"))
        for name in _string_list(entry.get("imports", []))
    )
    return FrontendAssets(script=script, styles=styles, preloads=preloads)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrontendAssetError("Frontend manifest is unavailable") from exc
    if not isinstance(value, dict):
        raise FrontendAssetError("Frontend manifest is invalid")
    return value


def _manifest_chunk(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    chunk = manifest.get(name)
    if not isinstance(chunk, dict):
        raise FrontendAssetError("Frontend dependency is missing")
    return chunk


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise FrontendAssetError("Frontend asset list is invalid")
    return value


def _asset_url(asset_root: Path, value: object) -> str:
    if not isinstance(value, str):
        raise FrontendAssetError("Frontend asset path is invalid")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise FrontendAssetError("Frontend asset path is unsafe")
    if not (asset_root / relative).is_file():
        raise FrontendAssetError("Frontend asset is unavailable")
    return f"/static/app/{relative.as_posix()}"


@router.get("/ui-preview")
@router.get("/ui-preview/{path:path}")
@router.get("/")
@router.get("/hosts")
@router.get("/vms")
@router.get("/vms/create")
@router.get("/vms/create/blank-disk")
@router.get("/vms/create/platform-image")
@router.get("/storage")
@router.get("/tasks")
@router.get("/media")
@router.get("/networks")
@router.get("/audit")
@router.get("/settings/account")
async def react_preview(request: Request, path: str = "") -> Response:
    return _react_shell(request)


@router.get("/tasks/{task_id:uuid}")
async def react_task_detail(request: Request) -> Response:
    return _react_shell(request)


@router.get("/media/{media_item_id:uuid}/copy")
async def react_media_copy(request: Request) -> Response:
    return _react_shell(request)


@router.get("/hosts/new")
@router.get("/hosts/{host_id}/confirm")
async def react_host_onboarding(request: Request) -> Response:
    return _react_shell(request)


@router.get("/hosts/{host_id}")
@router.get("/manage/hosts/{host_id}")
@router.get("/hosts/{host_id}/remove")
async def react_host_detail(request: Request) -> Response:
    return _react_shell(request)


@router.get("/hosts/{host_id}/vms/{domain_uuid}")
async def react_vm_detail(request: Request) -> Response:
    return _react_shell(request)


@router.get("/hosts/{host_id}/vms/{domain_uuid}/config")
@router.get("/manage/hosts/{host_id}/vms/{domain_uuid}")
async def react_vm_configuration(request: Request) -> Response:
    return _react_shell(request)


def _react_shell(request: Request) -> Response:
    auth_service: AuthService = request.app.state.auth_service
    session_service: SessionService = request.app.state.session_service
    if not auth_service.is_initialized():
        return RedirectResponse("/initialize", status_code=status.HTTP_303_SEE_OTHER)
    if session_service.resolve(request.cookies.get(SESSION_COOKIE)) is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return render_react_shell(request)


def render_react_shell(
    request: Request,
    *,
    auth_mode: str | None = None,
    auth_error: str | None = None,
    auth_csrf: str | None = None,
    status_code: int = 200,
) -> Response:
    try:
        assets = load_frontend_assets()
    except FrontendAssetError:
        return PlainTextResponse(
            "Frontend assets unavailable",
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    return templates.TemplateResponse(
        request=request,
        name="react_shell.html",
        context={
            "assets": assets,
            "csp_nonce": request.state.csp_nonce,
            "auth_mode": auth_mode,
            "auth_error": auth_error,
            "auth_csrf": auth_csrf,
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )
