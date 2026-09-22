"""History and audit trail router."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Response

from apps.api.session import session_manager
from apps.api.security import get_workspace_guard

router = APIRouter(prefix="/history", tags=["history"])

@router.get("/{workspace_id}")
def get_history(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> List[Dict[str, Any]]:
    return session_manager.query_history.get(workspace_id, [])

@router.delete("/{workspace_id}")
def clear_history(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> Response:
    session_manager.query_history[workspace_id] = []
    session_manager.active_proposals.pop(workspace_id, None)
    session_manager.save(active_workspace_id=workspace_id)
    return Response(status_code=204)
