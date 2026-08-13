"""Security headers middleware."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from backend.app.core.config import Settings


async def add_security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    settings: Settings,
) -> Response:
    """Add conservative security headers.

    HTTPS termination is expected at a reverse proxy in production. HSTS is only
    emitted when `API_BASE_URL` is configured with https://.
    """

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if settings.is_https_enabled:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response
