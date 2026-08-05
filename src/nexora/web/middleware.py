"""Security response middleware."""

import secrets

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Attach conservative browser security headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        nonce = secrets.token_urlsafe(24)
        scope.setdefault("state", {})["csp_nonce"] = nonce

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["content-security-policy"] = (
                    "default-src 'self'; "
                    f"style-src-elem 'self' 'nonce-{nonce}'; "
                    "style-src-attr 'unsafe-inline'; img-src 'self' data:; "
                    f"script-src 'self' 'nonce-{nonce}'; "
                    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
                )
                headers["x-content-type-options"] = "nosniff"
                headers["referrer-policy"] = "no-referrer"
                headers["x-frame-options"] = "DENY"
            await send(message)

        await self.app(scope, receive, send_with_headers)
