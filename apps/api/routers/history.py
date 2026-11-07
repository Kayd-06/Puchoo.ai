"""History and audit trail router."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from apps.api.session import session_manager
from apps.api.security import get_workspace_guard, require_capability, require_workspace_admin, tenant_owner_id
from apps.core.chat_memory import ChatMemoryError, get_chat_memory
from backend.routers.auth import current_user

router = APIRouter(prefix="/history", tags=["history"])

@router.get("/{workspace_id}")
def get_history(
    workspace_id: str,
    workspace: Dict = Depends(get_workspace_guard),
    user=Depends(require_capability("view_history")),
) -> List[Dict[str, Any]]:
    return session_manager.get_history(workspace_id)

@router.delete("/{workspace_id}")
def clear_history(
    workspace_id: str,
    workspace: Dict = Depends(require_workspace_admin),
    user=Depends(current_user),
) -> Response:
    return _delete(workspace_id, tenant_owner_id(user))


def _delete(workspace_id, tenant_id, record_id=None):
    from backend.memory_deletions import retry_deletions
    intent = session_manager.delete_history(tenant_id, workspace_id, record_id)
    try:
        pending = retry_deletions(intent_id=intent, limit=1)
    except Exception:
        # Logical deletion already committed; never misreport it as undone.
        pending = True
    if pending:
        return JSONResponse(status_code=202, content={"status": "deleted", "cleanup_pending": True})
    return Response(status_code=204)



@router.delete("/{workspace_id}/records/{record_id}")
def delete_history_record(
    workspace_id: str,
    record_id: str,
    workspace: Dict = Depends(require_workspace_admin),
    user=Depends(current_user),
) -> Response:
    """Permanently remove one history record and its scoped approved memory.

    Only workspace administrators can mutate history.  The record is resolved
    inside the selected workspace before its Chroma memory entry is touched.
    """

    # An absent record is an idempotent no-op inside the already authorized workspace.
    return _delete(workspace_id, tenant_owner_id(user), record_id)



@router.get("/{workspace_id}/memory/search")
def search_approved_memory(
    workspace_id: str,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=5, ge=1, le=10),
    workspace: Dict = Depends(get_workspace_guard),
    user=Depends(require_capability("view_history")),
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
