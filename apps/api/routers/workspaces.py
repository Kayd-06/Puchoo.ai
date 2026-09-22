"""Workspaces router for managing database connections and schemas."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from pydantic import BaseModel

from apps.core.workspaces import (
    create_server_workspace,
    create_sqlite_workspace,
    create_tabular_workspace,
    create_uploaded_sqlite_workspace,
    get_schema_metrics,
    get_schema_snapshot,
    get_schema_table_stats,
)
from apps.api.session import session_manager
from apps.api.security import get_workspace_guard

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

class ServerWorkspaceRequest(BaseModel):
    name: str
    engine: str
    host: str
    port: int
    database: str
    username: str
    password: str
    ssl_required: bool = True

@router.get("/")
def list_workspaces() -> List[Dict[str, Any]]:
    return list(session_manager.workspaces.values())

@router.post("/server")
def connect_server(request: ServerWorkspaceRequest) -> Dict[str, Any]:
    try:
        workspace = create_server_workspace(
            request.name,
            engine=request.engine, # type: ignore
            host=request.host,
            port=request.port,
            database=request.database,
            username=request.username,
            password=request.password,
            ssl_required=request.ssl_required,
        )
        ws_dict = workspace.as_dict()
        session_manager.add_workspace(ws_dict)
        return ws_dict
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    name: str = Form(""),
) -> Dict[str, Any]:
    contents = await file.read()
    filename = file.filename or "uploaded_file"
    ws_name = name.strip() or filename.rsplit(".", 1)[0]
    
    try:
        if filename.lower().endswith((".db", ".sqlite", ".sqlite3")):
            workspace = create_uploaded_sqlite_workspace(ws_name, filename, contents)
        elif filename.lower().endswith((".csv", ".xlsx", ".xls")):
            workspace = create_tabular_workspace(ws_name, filename, contents)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format")
            
        ws_dict = workspace.as_dict()
        session_manager.add_workspace(ws_dict)
        return ws_dict
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{workspace_id}")
def get_workspace(workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, Any]:
    return workspace

@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> Response:
    session_manager.remove_workspace(workspace_id)
    return Response(status_code=204)

@router.get("/{workspace_id}/schema")
def get_schema(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, str]:
    cache_key = f"schema_{workspace_id}"
    if cache_key not in session_manager.schema_snapshots:
        try:
            session_manager.schema_snapshots[cache_key] = get_schema_snapshot(workspace["database_uri"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"schema": session_manager.schema_snapshots[cache_key]}

@router.post("/{workspace_id}/schema/refresh")
def refresh_schema(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, str]:
    try:
        schema = get_schema_snapshot(workspace["database_uri"])
        session_manager.schema_snapshots[f"schema_{workspace_id}"] = schema
        return {"schema": schema}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{workspace_id}/metrics")
def get_metrics(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, int]:
    try:
        return get_schema_metrics(workspace["database_uri"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{workspace_id}/tables")
def get_tables(workspace_id: str, workspace: Dict = Depends(get_workspace_guard)) -> List[Dict[str, Any]]:
    local_source = workspace.get("source_type") in {"spreadsheet", "file"}
    try:
        stats = get_schema_table_stats(workspace["database_uri"], include_row_counts=local_source)
        return stats # type: ignore
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
