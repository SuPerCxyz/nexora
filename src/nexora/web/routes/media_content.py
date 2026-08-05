"""Credential-protected streaming ISO content endpoint."""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from starlette.responses import Response, StreamingResponse

from nexora.media.credentials import MediaCredentialError, MediaCredentialService
from nexora.media.ranges import (
    ByteRange,
    MediaRangeError,
    open_indexed_media,
    parse_range,
)

router = APIRouter(include_in_schema=False)


@router.api_route(
    "/media/content/{credential_id}",
    methods=["GET", "HEAD"],
    name="media_content",
)
async def media_content(request: Request, credential_id: str) -> Response:
    token = _bearer_token(request.headers.get("authorization"))
    service: MediaCredentialService = request.app.state.media_credential_service
    try:
        if token:
            item = service.authenticate(credential_id, token)
        else:
            client_ip = request.client.host if request.client is not None else ""
            item = service.authenticate_node(credential_id, client_ip)
        opened = open_indexed_media(request.app.state.settings.library_dir, item)
    except (MediaCredentialError, OSError, ValueError):
        return PlainTextResponse(
            "Media credential or file is unavailable",
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    etag = f'"{item.sha256}"'
    common_headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": "private, no-store",
    }
    selected = ByteRange(0, opened.size_bytes - 1)
    response_status = 200
    range_header = request.headers.get("range")
    if range_header and request.headers.get("if-range", etag) == etag:
        try:
            selected = parse_range(range_header, opened.size_bytes)
        except MediaRangeError:
            opened.close()
            return Response(
                status_code=416,
                headers={
                    **common_headers,
                    "Content-Range": f"bytes */{item.size_bytes}",
                },
            )
        response_status = 206
        common_headers["Content-Range"] = (
            f"bytes {selected.start}-{selected.end}/{opened.size_bytes}"
        )
    common_headers["Content-Length"] = str(max(0, selected.length))
    if request.method == "HEAD":
        opened.close()
        return Response(status_code=response_status, headers=common_headers)
    return StreamingResponse(
        opened.chunks(selected),
        status_code=response_status,
        headers=common_headers,
        media_type="application/x-iso9660-image",
    )


def _bearer_token(value: str | None) -> str:
    if value is None or not value.startswith("Bearer "):
        return ""
    token = value.removeprefix("Bearer ")
    return token if " " not in token else ""
