"""Query generation, validation, and execution router."""

import os
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.core.executor import QueryExecutionError, ReadOnlyExecutor
from apps.core.guardrails import SQLGuardrailError
from apps.core.llm_client import (
    AnthropicConfigurationError,
    LocalMLXConfigurationError,
    LocalMLXSQLClient,
    SQLGenerationError,
    get_local_sql_repair_client,
    get_sql_client,
    local_semantic_feedback,
    question_clarification,
    compact_plan_feedback,
)
from apps.core.verification import ClaudeVerifier, VerificationStatus, verification_unavailable
from apps.core.workspaces import get_schema_snapshot
from apps.api.session import session_manager
from apps.api.security import get_workspace_guard

router = APIRouter(prefix="/query", tags=["query"])

class GenerateRequest(BaseModel):
    question: str

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@router.post("/{workspace_id}/generate")
def generate_query(workspace_id: str, request: GenerateRequest, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, Any]:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    controls = session_manager.get_guardrails(workspace_id)
    
    try:
        schema = session_manager.schema_snapshots.get(f"schema_{workspace_id}") or get_schema_snapshot(workspace["database_uri"])
        clarification = question_clarification(schema, question)
        if clarification:
            return {
                "status": "clarification_required",
                "question": question,
                **clarification,
            }
        executor = ReadOnlyExecutor(
            workspace["database_uri"], 
            max_rows=controls["max_rows"], 
            dialect=workspace.get("dialect", "sqlite"), 
            timeout_seconds=controls["timeout_seconds"]
        )
        client = get_sql_client()
        repair_client = get_local_sql_repair_client() if isinstance(client, LocalMLXSQLClient) else None
        
        if isinstance(client, LocalMLXSQLClient):
            try:
                max_attempts = max(2, min(int(os.getenv("LOCAL_SQL_MAX_ATTEMPTS", "4")), 5))
            except ValueError:
                max_attempts = 3
                
            feedback: List[str] = []
            previous_sql: Optional[str] = None
            guarded = None
            generated_sql = ""
            attempt = 1
            
            for attempt in range(1, max_attempts + 1):
                attempt_client = (
                    repair_client
                    if repair_client is not None and feedback and attempt % 2 == 0
                    else client
                )
                try:
                    generated_sql = attempt_client.generate_sql(
                        schema=schema,
                        question=question,
                        feedback=feedback if feedback else None,
                        previous_sql=previous_sql,
                    )
                except LocalMLXConfigurationError:
                    if attempt_client is client:
                        if repair_client is None:
                            raise
                        generated_sql = repair_client.generate_sql(
                            schema=schema,
                            question=question,
                            feedback=feedback if feedback else None,
                            previous_sql=previous_sql,
                        )
                    else:
                        generated_sql = client.generate_sql(
                            schema=schema,
                            question=question,
                            feedback=feedback if feedback else None,
                            previous_sql=previous_sql,
                        )
                feedback = local_semantic_feedback(question, generated_sql, schema)
                try:
                    guarded = executor.validate_query_plan(generated_sql)
                except (SQLGuardrailError, QueryExecutionError) as exc:
                    feedback.insert(0, compact_plan_feedback(exc, generated_sql))
                    
                if not feedback:
                    break
                previous_sql = generated_sql
                
            if guarded is None or feedback:
                raise SQLGenerationError(
                    "The local model could not produce a safe, executable query after repair attempts. "
                    "Try rephrasing the question."
                )
        else:
            attempt = 1
            generated_sql = client.generate_sql(schema=schema, question=question)
            guarded = executor.validate_query_plan(generated_sql)

        proposal = {
            "id": f"qry_{uuid4().hex[:12]}", 
            "workspace_id": workspace_id, 
            "question": question,
            "sql": guarded.sql, 
            "limit": guarded.limit, 
            "created_at": utc_now(),
            "model_attempts": attempt,
            "status": "proposed"
        }
        session_manager.active_proposals[workspace_id] = proposal
        return proposal
        
    except SQLGuardrailError as exc:
        blocked_record = {
            "id": f"qry_{uuid4().hex[:12]}", "workspace_id": workspace_id, "question": question,
            "sql": "", "status": "blocked", "created_at": utc_now(), "row_count": 0, "rows": [], "elapsed_ms": 0,
            "verification": {"status": "BLOCKED", "summary": "Blocked before execution.", "details": str(exc)},
        }
        session_manager.query_history.setdefault(workspace_id, []).insert(0, blocked_record)
        session_manager.save(active_workspace_id=workspace_id)
        raise HTTPException(status_code=403, detail=f"Blocked for safety: {exc}")
        
    except (AnthropicConfigurationError, LocalMLXConfigurationError, QueryExecutionError, SQLGenerationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

class ExecuteRequest(BaseModel):
    proposal_id: str

@router.post("/{workspace_id}/execute")
def execute_query(workspace_id: str, request: ExecuteRequest, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, Any]:
    proposal = session_manager.active_proposals.get(workspace_id)
    
    if not proposal or proposal["id"] != request.proposal_id:
        raise HTTPException(status_code=400, detail="Invalid or expired proposal.")

    controls = session_manager.get_guardrails(workspace_id)
    
    try:
        executor = ReadOnlyExecutor(
            workspace["database_uri"], 
            max_rows=controls["max_rows"], 
            dialect=workspace.get("dialect", "sqlite"), 
            timeout_seconds=controls["timeout_seconds"]
        )
        
        result = executor.execute(proposal["sql"])
        
        try:
            verification = ClaudeVerifier().verify(
                question=proposal["question"],
                sql=result.sql,
                columns=result.columns,
                rows=result.rows,
                row_count=result.row_count,
            )
            verification_dict = verification.as_dict()
        except RuntimeError as exc:
            verification_dict = verification_unavailable(str(exc)).as_dict()
            
        record = {
            **proposal,
            "status": "executed",
            "sql": result.sql,
            "row_count": result.row_count,
            "rows": result.rows,
            "columns": result.columns,
            "elapsed_ms": result.elapsed_ms,
            "verification": verification_dict,
            "executed_at": utc_now(),
        }
        
        session_manager.query_history.setdefault(workspace_id, []).insert(0, record)
        session_manager.active_proposals.pop(workspace_id, None)
        session_manager.save(active_workspace_id=workspace_id)
        
        # Build presentation data to match the UI behavior
        from apps.core.result_presentation import build_result_presentation
        presentation = build_result_presentation(record["question"], record["columns"], record["rows"])
        
        return {
            "record": record,
            "presentation": {
                "headline": presentation.headline,
                "detail": presentation.detail,
                "highlights": presentation.highlights
            }
        }
        
    except (QueryExecutionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
