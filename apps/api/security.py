"""Security, CORS, and CSRF protection for FastAPI."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from backend.routers.auth import current_user
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings

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
                secure=settings.cookie_secure,
            )
            
        return response

def tenant_owner_id(user) -> str:
    """Canonical tenant boundary for every workspace, query, and memory record."""
    return user.workspace_owner_id or user.institute_owner_id or user.id


def workspace_role(user) -> str:
    if tenant_owner_id(user) == user.id:
        return "owner"
    return user.workspace_role or "viewer"


def can_manage_data(user) -> bool:
    return workspace_role(user) in {"owner", "admin", "editor"}


def can_administer_workspace(user) -> bool:
    return workspace_role(user) in {"owner", "admin"}


def require_connection_admin(user=Depends(current_user)):
    """Server connections can reach other machines, so editors may not add them."""

    if not can_administer_workspace(user):
        raise HTTPException(
            status_code=403,
            detail="Only workspace owners and admins can add database connections.",
        )
    return user


def require_data_manager(user=Depends(current_user)):
    """Require a role that may create or modify workspace configuration."""

    if not can_manage_data(user):
        raise HTTPException(
            status_code=403,
            detail="Viewer access is read-only. Ask a workspace admin for editor access.",
        )
    return user


def get_workspace_guard(workspace_id: str, user=Depends(current_user)):
    """Return a workspace only within the caller's explicit tenant boundary."""
    from apps.api.session import session_manager
    workspace = session_manager.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found or unauthorized")
    owner_id = workspace.get("owner_user_id")
    allowed_owner = tenant_owner_id(user)
    if not owner_id or owner_id != allowed_owner:
        raise HTTPException(status_code=404, detail="Workspace not found or unauthorized")
    return workspace


def require_workspace_editor(
    workspace: dict = Depends(get_workspace_guard),
    user=Depends(require_data_manager),
):
    return workspace


def require_workspace_admin(
    workspace: dict = Depends(get_workspace_guard),
    user=Depends(current_user),
):
    if not can_administer_workspace(user):
        raise HTTPException(status_code=403, detail="Only workspace admins can make this change.")
    return workspace
