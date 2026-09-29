"""History and audit trail router."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from apps.api.session import session_manager
from apps.api.security import get_workspace_guard, require_workspace_admin, tenant_owner_id
from apps.core.chat_memory import ChatMemoryError, get_chat_memory
from backend.routers.auth import current_user

router = APIRouter(prefix="/history", tags=["history"])

@router.get("/{workspace_id}")
def get_history(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> List[Dict[str, Any]]:
    return session_manager.query_history.get(workspace_id, [])

@router.delete("/{workspace_id}")
def clear_history(
    workspace_id: str,
    workspace: Dict = Depends(require_workspace_admin),
    user=Depends(current_user),
) -> Response:
    session_manager.query_history[workspace_id] = []
    session_manager.active_proposals.pop(workspace_id, None)
    session_manager.save(active_workspace_id=workspace_id)
    try:
        get_chat_memory().delete_workspace_memory(
            tenant_id=tenant_owner_id(user),
            workspace_id=workspace_id,
        )
    except ChatMemoryError as exc:
        raise HTTPException(status_code=503, detail="Approved conversation memory is temporarily unavailable.") from exc
    return Response(status_code=204)


@router.get("/{workspace_id}/memory/search")
def search_approved_memory(
    workspace_id: str,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=5, ge=1, le=10),
    workspace: Dict = Depends(get_workspace_guard),
    user=Depends(current_user),
) -> Dict[str, Any]:
    """Semantic recall of approved conversations, strictly within this tenant/workspace."""

    try:
        matches = get_chat_memory().search_approved_conversations(
            tenant_id=tenant_owner_id(user),
            workspace_id=workspace_id,
            query=q,
            limit=limit,
        )
    except ChatMemoryError as exc:
        raise HTTPException(status_code=503, detail="Approved conversation memory is temporarily unavailable.") from exc
    return {"matches": matches}
