"""Canonical tenant roles and capability policy.

The API and frontend receive the same deny-by-default capability contract;
route dependencies still enforce every capability on the server.
"""

from typing import Literal, get_args

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from backend.models import User

EffectiveRole = Literal["owner", "admin", "editor", "viewer"]
CapabilityName = Literal[
    "view_workspaces",
    "view_history",
    "query_workspace",
    "manage_data_sources",
    "administer_workspace",
    "manage_account",
]


class AccountCapabilities(BaseModel):
    view_workspaces: bool = False
    view_history: bool = False
    query_workspace: bool = False
    manage_data_sources: bool = False
    administer_workspace: bool = False
    manage_account: bool = False


_CAPABILITIES: dict[EffectiveRole, AccountCapabilities] = {
    "owner": AccountCapabilities(
        view_workspaces=True,
        view_history=True,
        query_workspace=True,
        manage_data_sources=True,
        administer_workspace=True,
        manage_account=True,
    ),
    "admin": AccountCapabilities(
        view_workspaces=True,
        view_history=True,
        query_workspace=True,
        manage_data_sources=True,
        administer_workspace=True,
        manage_account=True,
    ),
    "editor": AccountCapabilities(
        view_workspaces=True,
        view_history=True,
        query_workspace=True,
        manage_account=True,
    ),
    "viewer": AccountCapabilities(
        view_workspaces=True,
        view_history=True,
        manage_account=True,
    ),
}


def tenant_id_for(user: User) -> str:
    return user.workspace_owner_id or user.institute_owner_id or user.id


def effective_role(user: User) -> EffectiveRole:
    if tenant_id_for(user) == user.id:
        return "owner"
    candidate = user.workspace_role or "viewer"
    return candidate if candidate in get_args(EffectiveRole) else "viewer"


def capabilities_for(user: User) -> AccountCapabilities:
    return _CAPABILITIES[effective_role(user)].model_copy()


def require_capability(name: CapabilityName):
    """Return a FastAPI dependency that authorizes one canonical capability."""

    from backend.routers.auth import current_user

    def dependency(user: User = Depends(current_user)) -> User:
        if not getattr(capabilities_for(user), name, False):
            raise HTTPException(status_code=403, detail="Your workspace role does not allow this action.")
        return user

    return dependency
