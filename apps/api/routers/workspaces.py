"""Workspaces router for managing database connections and schemas."""

import logging
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from pydantic import BaseModel, ValidationError, field_validator, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from backend.routers.auth import current_user
from backend.database import get_db
from backend.notifications import create_notification
from backend.rate_limit import connection_limiter

from apps.core.db_connection import (
    GENERIC_CONNECTION_ERROR,
    GENERIC_HOST_ERRORS,
    DatabaseConnectionError,
    ServerConnection,
)
from apps.core.workspaces import (
    create_server_workspace,
    create_sqlite_workspace,
    create_tabular_workspace,
    create_tabular_collection_workspace,
    create_uploaded_sqlite_workspace,
    get_schema_metrics,
    get_schema_snapshot,
    get_schema_table_stats,
)
from apps.api.session import session_manager
from apps.api.security import (
    require_connection_admin,
    require_data_manager,
    require_workspace_admin,
    require_workspace_editor,
    tenant_owner_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
PUBLIC_WORKSPACE_FIELDS = ("id", "name", "dialect", "source_type")

class ServerWorkspaceRequest(BaseModel):
    name: str
    engine: str
    host: str
    port: int
    database: str
    username: str
    password: str
    # Accepted so older clients still validate. TLS is a server setting.
    ssl_required: bool = True

    @field_validator("engine")
    @classmethod
    def known_engine(cls, value: str) -> str:
        if value not in {"postgresql", "mysql"}:
            raise ValueError("Dialect must be postgresql or mysql.")
        return value

    @model_validator(mode="before")
    @classmethod
    def connection_fields(cls, data: object) -> object:
        """Validate the raw body so port strings and booleans are not coerced first."""

        if not isinstance(data, dict):
            return data
        try:
            ServerConnection(
                dialect=data.get("engine"),
                host=data.get("host"),
                port=data.get("port"),
                database=data.get("database"),
                username=data.get("username"),
                password=data.get("password"),
            )
        except ValidationError as exc:
            message = str(exc.errors()[0].get("msg", "Check the connection details and try again."))
            prefix = "Value error, "
            if message.startswith(prefix):
                message = message[len(prefix):]
            raise ValueError(message) from None
        return data

def _owner_id(user) -> str:
    return tenant_owner_id(user)


def _public_workspace(workspace: Dict[str, Any]) -> Dict[str, Any]:
    """Never send database URIs (which may embed passwords) to a browser."""

    return {field: workspace[field] for field in PUBLIC_WORKSPACE_FIELDS if field in workspace}

@router.get("/")
def list_workspaces(user=Depends(current_user)) -> List[Dict[str, Any]]:
    owner_id = _owner_id(user)
    return [
        _public_workspace(workspace)
        for workspace in session_manager.workspaces.values()
        if workspace.get("owner_user_id") == owner_id
    ]

def _source_connect_args(workspace: Dict[str, Any]) -> dict | None:
    value = workspace.get("connect_args")
    return value if isinstance(value, dict) else None


@router.post("/server")
def connect_server(request: ServerWorkspaceRequest, user=Depends(require_connection_admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    if not connection_limiter.allow([f"db-connect:{user.id}"]):
        raise HTTPException(
            status_code=429,
            detail="Too many connection attempts. Try again later.",
            headers={"Retry-After": "900"},
        )
    try:
        workspace = create_server_workspace(
            request.name,
            engine=request.engine,  # type: ignore[arg-type]
            host=request.host,
            port=request.port,
            database=request.database,
            username=request.username,
            password=request.password,
        )
        ws_dict = workspace.as_dict()
        ws_dict["owner_user_id"] = _owner_id(user)
        session_manager.add_workspace(ws_dict)
        create_notification(db, user_id=user.id, kind="workspace_connected", title="Database connected", body=f"{workspace.name} is ready for read-only questions.", resource_id=workspace.id)
        db.commit()
        return _public_workspace(ws_dict)
    except DatabaseConnectionError:
        raise HTTPException(status_code=400, detail=GENERIC_CONNECTION_ERROR) from None
    except SQLAlchemyError as exc:
        logger.warning("database connection failed: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail=GENERIC_CONNECTION_ERROR) from None
    except ValueError as exc:
        if str(exc) in GENERIC_HOST_ERRORS:
            logger.info("database host rejected")
            raise HTTPException(status_code=400, detail=GENERIC_CONNECTION_ERROR) from None
        raise HTTPException(status_code=400, detail=str(exc)) from None

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    name: str = Form(""),
    user=Depends(require_data_manager),
    db: Session = Depends(get_db),
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
        ws_dict["owner_user_id"] = _owner_id(user)
        session_manager.add_workspace(ws_dict)
        create_notification(db, user_id=user.id, kind="workspace_uploaded", title="Data source added", body=f"{workspace.name} is ready for read-only questions.", resource_id=workspace.id)
        db.commit()
        return _public_workspace(ws_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    name: str = Form(""),
    user=Depends(require_data_manager),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one CSV or Excel file")
    payloads: list[tuple[str, bytes]] = []
    for file in files:
        filename = file.filename or "uploaded_file"
        if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
            raise HTTPException(
                status_code=400,
                detail="Multiple upload supports CSV and Excel files only. Upload SQLite databases individually.",
            )
        payloads.append((filename, await file.read()))
    workspace_name = name.strip() or f"{len(payloads)}-file workspace"
    try:
        workspace = create_tabular_collection_workspace(workspace_name, payloads)
        ws_dict = workspace.as_dict()
        ws_dict["owner_user_id"] = _owner_id(user)
        session_manager.add_workspace(ws_dict)
        create_notification(db, user_id=user.id, kind="workspace_uploaded", title="Data sources added", body=f"{workspace.name} is ready for read-only questions.", resource_id=workspace.id)
        db.commit()
        return _public_workspace(ws_dict)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/{workspace_id}")
def get_workspace(workspace: Dict = Depends(require_workspace_editor)) -> Dict[str, Any]:
    return _public_workspace(workspace)

@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: str, workspace: Dict = Depends(require_workspace_admin)) -> Response:
    session_manager.remove_workspace(workspace_id)
    return Response(status_code=204)

@router.get("/{workspace_id}/schema")
def get_schema(workspace_id: str, workspace: Dict = Depends(require_workspace_editor)) -> Dict[str, str]:
    cache_key = f"schema_{workspace_id}"
    if cache_key not in session_manager.schema_snapshots:
        try:
            session_manager.schema_snapshots[cache_key] = get_schema_snapshot(
                workspace["database_uri"], connect_args=_source_connect_args(workspace)
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"schema": session_manager.schema_snapshots[cache_key]}

@router.post("/{workspace_id}/schema/refresh")
def refresh_schema(workspace_id: str, workspace: Dict = Depends(require_workspace_editor)) -> Dict[str, str]:
    try:
        schema = get_schema_snapshot(workspace["database_uri"], connect_args=_source_connect_args(workspace))
        session_manager.schema_snapshots[f"schema_{workspace_id}"] = schema
        return {"schema": schema}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{workspace_id}/metrics")
def get_metrics(workspace_id: str, workspace: Dict = Depends(require_workspace_editor)) -> Dict[str, int]:
    try:
        return get_schema_metrics(workspace["database_uri"], connect_args=_source_connect_args(workspace))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{workspace_id}/tables")
def get_tables(workspace_id: str, workspace: Dict = Depends(require_workspace_editor)) -> List[Dict[str, Any]]:
    local_source = workspace.get("source_type") in {"spreadsheet", "spreadsheet_collection", "file"}
    try:
        stats = get_schema_table_stats(
            workspace["database_uri"],
            include_row_counts=local_source,
            connect_args=_source_connect_args(workspace),
        )
        return stats # type: ignore
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
