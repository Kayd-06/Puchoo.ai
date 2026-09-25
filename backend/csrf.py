"""Attach the double-submit CSRF cookie. Route handlers reject mismatches."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.config import settings
from backend.security import set_csrf_cookie


def _response_sets_cookie(response, name: str) -> bool:
    prefix = f"{name}=".encode()
    for key, value in response.raw_headers:
        if key.lower() == b"set-cookie" and value.startswith(prefix):
            return True
    return False


class CSRFCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if settings.csrf_cookie_name in request.cookies:
            return response
        if _response_sets_cookie(response, settings.csrf_cookie_name):
            return response
        set_csrf_cookie(response)
        return response
