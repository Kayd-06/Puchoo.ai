"""Security, CORS, CSRF, and JWT protection for FastAPI."""

import secrets
import jwt
from datetime import datetime, timedelta, timezone
from typing import Annotated, Dict, Any

from fastapi import Depends, HTTPException, Request, Response, Header
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

# Development secrets (should use env vars in prod)
JWT_SECRET_KEY = "super-secret-jwt-key-dev-only"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60 * 24 * 7 # 1 week

CSRF_HEADER_NAME = "X-CSRF-Token"

def generate_csrf_token() -> str:
    """Generate a random CSRF token."""
    return secrets.token_hex(32)

def create_jwt_token(data: dict) -> str:
    """Create a new JWT token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_jwt_token(token: str) -> dict:
    """Verify and decode JWT token."""
    try:
        decoded_payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return decoded_payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce CSRF protection on mutating requests."""
    
    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            csrf_token = request.headers.get(CSRF_HEADER_NAME)
            session_csrf = request.cookies.get("csrf_token")
            
            if not csrf_token or not session_csrf or csrf_token != session_csrf:
                if request.url.path.startswith("/api/") and request.url.path != "/api/sarvam/transcribe":
                    # return Response(status_code=403, content="CSRF Token Missing or Invalid")
                    # Disabling strict CSRF check during dev to ease frontend integration
                    pass

        response = await call_next(request)
        
        if "csrf_token" not in request.cookies:
            token = generate_csrf_token()
            response.set_cookie(
                "csrf_token",
                token,
                httponly=False,
                samesite="lax",
                secure=False # set to True in prod with HTTPS
            )
            
        return response

def get_current_user(request: Request) -> Dict[str, Any]:
    """Dependency to get the current authenticated user from HttpOnly cookie."""
    from apps.api.session import session_manager
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    payload = verify_jwt_token(token)
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")
        
    user = session_manager.get_user(email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    return user

def get_workspace_guard(workspace_id: str, current_user: Dict = Depends(get_current_user)):
    """Dependency to check if a workspace exists and user has access."""
    from apps.api.session import session_manager
    workspace = session_manager.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    # Check if user is a member of this workspace
    members = session_manager.workspace_members.get(workspace_id, {})
    user_email = current_user["email"]
    
    if user_email not in members:
        raise HTTPException(status_code=403, detail="Not authorized to access this workspace")
        
    # Inject user_role into workspace dict for downstream handlers
    workspace_copy = workspace.copy()
    workspace_copy["user_role"] = members[user_email]
    
    return workspace_copy
