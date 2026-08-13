"""Token-based API authentication."""

from enum import StrEnum
from hmac import compare_digest

from fastapi import HTTPException, Request, status
from fastapi.security.utils import get_authorization_scheme_param

from backend.app.core.config import Settings


class AuthScope(StrEnum):
    """Supported API token scopes."""

    READ = "read"
    DEVICE = "device"
    ALERTS = "alerts"
    ADMIN = "admin"


def _extract_token(request: Request) -> str | None:
    """Read a bearer token or X-API-Token header from a request."""

    authorization = request.headers.get("Authorization")
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() == "bearer" and token:
        return token
    return request.headers.get("X-API-Token")


def _token_matches(candidate: str | None, expected: str | None) -> bool:
    """Compare tokens without leaking timing information."""

    if not candidate or not expected:
        return False
    return compare_digest(candidate, expected)


def require_scope(request: Request, settings: Settings, scope: AuthScope) -> AuthScope:
    """Validate the request token for the required scope."""

    if not settings.auth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API tokens are not configured",
        )

    token = _extract_token(request)
    if scope == AuthScope.READ:
        valid = _token_matches(token, settings.api_read_token) or _token_matches(token, settings.api_admin_token)
    elif scope == AuthScope.DEVICE:
        valid = _token_matches(token, settings.api_device_token) or _token_matches(token, settings.api_admin_token)
    elif scope == AuthScope.ALERTS:
        valid = _token_matches(token, settings.api_alerts_token) or _token_matches(token, settings.api_admin_token)
    else:
        valid = _token_matches(token, settings.api_admin_token)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return scope
