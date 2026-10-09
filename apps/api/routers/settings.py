"""Settings and guardrails router."""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from apps.api.session import session_manager
from apps.api.security import get_workspace_guard, require_workspace_admin
from backend.routers.auth import current_user

router = APIRouter(prefix="/settings", tags=["settings"])

class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120, strict=True)
    email: EmailStr
    department: str = Field(min_length=1, max_length=200, strict=True)
    timezone: str = Field(min_length=1, max_length=64, strict=True)

def _profile_response(user) -> Dict[str, str]:
    return {"name": user.full_name, "email": user.email, "department": user.institute_name or "Personal", "timezone": "UTC"}


@router.get("/profile")
def get_profile(user=Depends(current_user)) -> Dict[str, str]:
    return _profile_response(user)


@router.put("/profile")
def update_profile(request: ProfileRequest, user=Depends(current_user)) -> Dict[str, str]:
    """Do not allow a client to replace shared in-memory profile data.

    Profile values come from the verified account. Email changes must go
    through an OTP-confirmed account flow, rather than this generic endpoint.
    """

    raise HTTPException(status_code=409, detail="Profile changes require verified account settings.")

class GuardrailsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_rows: int = Field(ge=1, le=10_000, strict=True)
    timeout_seconds: int = Field(ge=1, le=300, strict=True)
    confirm_complex_queries: bool = Field(strict=True)

@router.get("/guardrails/{workspace_id}")
def get_guardrails(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, Any]:
    return session_manager.get_guardrails(workspace_id)

@router.put("/guardrails/{workspace_id}")
def update_guardrails(workspace_id: str, request: GuardrailsRequest, workspace: Dict = Depends(require_workspace_admin)) -> Dict[str, Any]:
    guardrails = {
        "max_rows": request.max_rows,
        "timeout_seconds": request.timeout_seconds,
        "confirm_complex_queries": request.confirm_complex_queries
    }
    session_manager.workspace_guardrails[workspace_id] = guardrails
    session_manager.save(active_workspace_id=workspace_id)
    return guardrails
