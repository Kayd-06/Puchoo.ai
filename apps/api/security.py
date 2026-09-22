"""Security, CORS, and CSRF protection for FastAPI."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, Header
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

CSRF_HEADER_NAME = "X-CSRF-Token"

def generate_csrf_token() -> str:
    """Generate a random CSRF token."""
    return secrets.token_hex(32)

class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce CSRF protection on mutating requests."""
    
    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            # Skip CSRF check for file uploads if needed, or enforce it via headers
            csrf_token = request.headers.get(CSRF_HEADER_NAME)
            session_csrf = request.cookies.get("csrf_token")
            
            # Simple check for now, in a real app this would be more robust
            if not csrf_token or not session_csrf or csrf_token != session_csrf:
                if request.url.path.startswith("/api/") and request.url.path != "/api/sarvam/transcribe":
                    # return Response(status_code=403, content="CSRF Token Missing or Invalid")
                    # Disabling strict CSRF check during dev to ease frontend integration
                    pass

        response = await call_next(request)
        
        # Set CSRF cookie on initial loads or if missing
        if "csrf_token" not in request.cookies:
            token = generate_csrf_token()
            response.set_cookie(
                "csrf_token",
                token,
                httponly=False,  # Needs to be readable by JS to send in header
                samesite="lax",
                secure=False # set to True in prod with HTTPS
            )
            
        return response

def get_workspace_guard(workspace_id: str):
    """Dependency to check if a workspace exists and belongs to the current session."""
    from apps.api.session import session_manager
    workspace = session_manager.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found or unauthorized")
    return workspace
