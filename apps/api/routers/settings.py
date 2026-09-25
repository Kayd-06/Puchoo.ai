"""Settings and guardrails router."""

from typing import Any, Dict
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.session import session_manager
from apps.api.security import get_workspace_guard
from backend.routers.auth import current_user

router = APIRouter(prefix="/settings", tags=["settings"])

class ProfileRequest(BaseModel):
    name: str
    email: str
    department: str
    timezone: str

@router.get("/profile")
def get_profile(user=Depends(current_user)) -> Dict[str, str]:
    return {"name": user.full_name, "email": user.email, "department": user.institute_name or "Personal", "timezone": "UTC"}

@router.put("/profile")
def update_profile(request: ProfileRequest) -> Dict[str, str]:
    session_manager.profile = {
        "name": request.name,
        "email": request.email,
        "department": request.department,
        "timezone": request.timezone
    }
    session_manager.save()
    return session_manager.profile

class GuardrailsRequest(BaseModel):
    max_rows: int
    timeout_seconds: int
    confirm_complex_queries: bool

@router.get("/guardrails/{workspace_id}")
def get_guardrails(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, Any]:
    return session_manager.get_guardrails(workspace_id)

@router.put("/guardrails/{workspace_id}")
def update_guardrails(workspace_id: str, request: GuardrailsRequest, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, Any]:
    guardrails = {
        "max_rows": request.max_rows,
        "timeout_seconds": request.timeout_seconds,
        "confirm_complex_queries": request.confirm_complex_queries
    }
    session_manager.workspace_guardrails[workspace_id] = guardrails
    session_manager.save(active_workspace_id=workspace_id)
    return guardrails
