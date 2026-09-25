"""Query generation, validation, and execution router."""

import json
import logging
import os
import re
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.core.executor import QueryExecutionError, ReadOnlyExecutor
from apps.core.guardrails import SQLGuardrailError, SQLParseError
from apps.core.llm_client import (
    AnthropicConfigurationError,
    LocalMLXConfigurationError,
    LocalMLXSQLClient,
    SQLGenerationError,
    get_sql_client,
    local_semantic_feedback,
    question_clarification,
    compact_plan_feedback,
    canonicalize_analytics_question,
    schema_guided_fallback_sql,
)
from apps.core.verification import get_verifier, verification_unavailable
from apps.core.workspaces import get_schema_snapshot
from apps.core.sarvam_client import SarvamClient, SarvamConfigurationError
from apps.core.semantic_layer import (
    build_query_plan,
    parse_schema,
    plan_semantic_feedback,
    render_planned_question,
    select_relevant_schema,
)
from apps.core.query_planning import (
    QueryPlanError,
    build_plan_sql_request,
    classify_complexity,
    plan_complex_query,
    plan_constraint_feedback,
    select_plan_schema,
)
from apps.api.session import session_manager
from apps.api.security import get_workspace_guard

router = APIRouter(prefix="/query", tags=["query"])
logger = logging.getLogger(__name__)
_translation_cache: dict[tuple[str, str], str] = {}

class GenerateRequest(BaseModel):
    question: str
    language_code: str | None = None

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_sql(sql: str) -> str:
    return re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"", "?", sql)


def _log_trace(trace: dict[str, Any]) -> None:
    logger.info("query_pipeline %s", json.dumps(trace, sort_keys=True, default=str))


def _plan_trace(plan: dict[str, Any]) -> dict[str, Any]:
    """Retain plan structure without logging question text or literal filter values."""

    return {
        "relevant_tables": plan.get("relevant_tables", plan.get("tables", [])),
        "metrics": plan.get("metrics", []),
        "group_by": plan.get("group_by", plan.get("dimensions", [])),
        "ranking": plan.get("ranking") or plan.get("order_by"),
        "needs_clarification": bool(plan.get("needs_clarification", False)),
        "filter_count": len(plan.get("filters", [])),
        "assumption_count": len(plan.get("assumptions", [])),
        "has_time_range": bool(plan.get("time_range")),
    }


def _schema_for_tables(schema: str, selected_tables: list[str]) -> str:
    selected = set(selected_tables)
    blocks = [table.block for table in parse_schema(schema) if table.name in selected]
    return "\n\n".join(blocks) if blocks else schema


def _autonomous_mode() -> bool:
    return os.getenv("PUCHOO_AUTONOMOUS_MODE", "true").strip().lower() not in {"0", "false", "no", "off"}


def _spoken_language(language_code: str | None) -> str | None:
    """Only pass a detected, non-English BCP-47 code to the language adapter."""

    if not isinstance(language_code, str):
        return None
    normalized = language_code.strip()
    if not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", normalized) or normalized == "en-IN":
        return None
    return normalized


def _infer_indic_language(question: str) -> str | None:
    """Best-effort script detection for typed questions without a voice language code."""

    script_languages = (
        (r"[\u0980-\u09ff]", "bn-IN"),  # Bengali
        (r"[\u0a00-\u0a7f]", "pa-IN"),  # Gurmukhi / Punjabi
        (r"[\u0a80-\u0aff]", "gu-IN"),  # Gujarati
        (r"[\u0b00-\u0b7f]", "od-IN"),  # Odia
        (r"[\u0b80-\u0bff]", "ta-IN"),  # Tamil
        (r"[\u0c00-\u0c7f]", "te-IN"),  # Telugu
        (r"[\u0c80-\u0cff]", "kn-IN"),  # Kannada
        (r"[\u0d00-\u0d7f]", "ml-IN"),  # Malayalam
        (r"[\u0600-\u06ff]", "ur-IN"),  # Urdu
        (r"[\u0900-\u097f]", "hi-IN"),  # Devanagari / Hindi default
    )
    return next((language for pattern, language in script_languages if re.search(pattern, question)), None)


def _translate_for_sql(question: str, language_code: str | None) -> str:
    if not language_code:
        return question
    try:
        return SarvamClient().translate(question, "en-IN", source_language=language_code)
    except (SarvamConfigurationError, RuntimeError, ValueError) as exc:
        raise ValueError("Could not translate the spoken question for SQL generation. Please try again.") from exc


def _translate_for_display(text: str, language_code: str | None) -> str:
    """Localisation should never hide an otherwise valid query result."""

    if not language_code or not text:
        return text
    cache_key = (language_code, text)
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]
    try:
        translated = SarvamClient().translate(text, language_code, source_language="en-IN")
        _translation_cache[cache_key] = translated
        return translated
    except (SarvamConfigurationError, RuntimeError, ValueError) as exc:
        logger.warning("result_translation_unavailable language=%s error=%s", language_code, exc)
        return text


def _localize_rows(rows: list[dict[str, Any]], language_code: str | None) -> list[dict[str, Any]]:
    """Translate visible text values, but preserve numeric facts and untranslatable data exactly."""

    if not language_code:
        return rows
    texts = [
        value.strip()
        for row in rows
        for value in row.values()
        if isinstance(value, str) and value.strip() and any(character.isalpha() for character in value)
    ]
    if not texts:
        return rows
    try:
        translations = SarvamClient().translate_many(texts, language_code, source_language="en-IN")
    except (SarvamConfigurationError, RuntimeError, ValueError) as exc:
        logger.warning("table_translation_unavailable language=%s error=%s", language_code, exc)
        return rows
    return [
        {
            key: translations.get(value.strip(), value) if isinstance(value, str) else value
            for key, value in row.items()
        }
        for row in rows
    ]

@router.post("/{workspace_id}/generate")
def generate_query(workspace_id: str, request: GenerateRequest, workspace: Dict = Depends(get_workspace_guard)) -> Dict[str, Any]:
    started = perf_counter()
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    language_code = _spoken_language(request.language_code) or _infer_indic_language(question)
    try:
        planning_question = canonicalize_analytics_question(
            _translate_for_sql(question, language_code)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    controls = session_manager.get_guardrails(workspace_id)
    
    try:
        schema = session_manager.schema_snapshots.get(f"schema_{workspace_id}") or get_schema_snapshot(workspace["database_uri"])
        autonomous = _autonomous_mode()
        clarification = None if autonomous else question_clarification(schema, planning_question)
        if clarification:
            return {
                "status": "clarification_required",
                "question": question,
                **clarification,
            }
        deterministic_sql = schema_guided_fallback_sql(schema, planning_question)
        decision = classify_complexity(planning_question, schema)
        client = get_sql_client()
        if deterministic_sql:
            intent_plan = build_query_plan(schema, planning_question)
            focused_schema = select_relevant_schema(schema, intent_plan)
            planned_question = render_planned_question(intent_plan)
            selected_tables = sorted(set(re.findall(r'(?:from|join)\s+["`\[]?([a-z_][\w]*)', deterministic_sql.lower())))
            public_plan = intent_plan.as_dict()
            structured_plan = None
            decision = type(decision)("deterministic_complex", decision.score, decision.reasons)
        elif decision.route == "planned":
            if not hasattr(client, "generate_plan"):
                raise SQLGenerationError("Complex-query planning requires a planner-capable model provider.")
            structured_plan = plan_complex_query(client, schema=schema, question=planning_question)
            if structured_plan.needs_clarification:
                if autonomous:
                    if structured_plan.clarification_question:
                        structured_plan.assumptions.append(
                            "Autonomous default applied instead of asking: "
                            + structured_plan.clarification_question
                        )
                    structured_plan.needs_clarification = False
                    structured_plan.clarification_question = None
                else:
                    _log_trace({
                        "route": decision.route, "plan_valid": True,
                        "plan": _plan_trace(structured_plan.as_dict()),
                        "selected_tables": structured_plan.relevant_tables, "validation_outcome": "clarification",
                        "retry_count": 0, "latency_ms": round((perf_counter() - started) * 1000),
                    })
                    return {
                        "status": "clarification_required",
                        "question": question,
                        "reason": "planner_clarification",
                        "message": _translate_for_display(structured_plan.clarification_question or "", language_code),
                        "suggestions": [],
                        "assumptions": [_translate_for_display(item, language_code) for item in structured_plan.assumptions],
                        "interpreted_request": _translate_for_display(structured_plan.normalized_question, language_code),
                    }
            focused_schema, selected_tables = select_plan_schema(schema, structured_plan)
            planned_question = build_plan_sql_request(planning_question, structured_plan)
            public_plan = structured_plan.as_dict()
        else:
            intent_plan = build_query_plan(schema, planning_question)
            focused_schema = select_relevant_schema(schema, intent_plan)
            planned_question = render_planned_question(intent_plan)
            selected_tables = intent_plan.tables
            public_plan = intent_plan.as_dict()
            structured_plan = None
        executor = ReadOnlyExecutor(
            workspace["database_uri"], 
            max_rows=controls["max_rows"], 
            dialect=workspace.get("dialect", "sqlite"), 
            timeout_seconds=controls["timeout_seconds"]
        )
        max_attempts = 1
        
        if isinstance(client, LocalMLXSQLClient):
            try:
                max_attempts = max(1, min(int(os.getenv("LOCAL_SQL_MAX_ATTEMPTS", "2")), 3))
            except ValueError:
                max_attempts = 2
                
            feedback: List[str] = []
            previous_sql: Optional[str] = None
            guarded = None
            generated_sql = ""
            attempt = 1
            if deterministic_sql:
                generated_sql = deterministic_sql
                guarded = executor.validate_query_plan(generated_sql)
                feedback = local_semantic_feedback(planning_question, generated_sql, schema)
                attempt = 0
            else:
                for attempt in range(1, max_attempts + 1):
                    generated_sql = client.generate_sql(
                        schema=focused_schema,
                        question=planned_question,
                        feedback=feedback if feedback else None,
                        previous_sql=previous_sql,
                    )
                    feedback = local_semantic_feedback(planning_question, generated_sql, schema)
                    if structured_plan is not None:
                        feedback.extend(plan_constraint_feedback(structured_plan, generated_sql))
                    else:
                        feedback.extend(plan_semantic_feedback(intent_plan, generated_sql))
                    try:
                        guarded = executor.validate_query_plan(generated_sql)
                    except SQLParseError as exc:
                        feedback.insert(0, str(exc) + " Return one complete, concise SQLite SELECT statement only.")
                    except SQLGuardrailError:
                        # Never send unsafe SQL back through a repair loop.
                        raise
                    except QueryExecutionError as exc:
                        feedback.insert(0, f"Exact database error: {exc.database_error}")
                        feedback.insert(0, compact_plan_feedback(Exception(exc.database_error), generated_sql))

                    if not feedback:
                        break
                    previous_sql = generated_sql
                
            if guarded is None or feedback:
                fallback_sql = schema_guided_fallback_sql(schema, planning_question)
                if fallback_sql:
                    generated_sql = fallback_sql
                    guarded = executor.validate_query_plan(generated_sql)
                    feedback = local_semantic_feedback(planning_question, generated_sql, schema)
                    if structured_plan is not None:
                        feedback.extend(plan_constraint_feedback(structured_plan, generated_sql))
                    else:
                        feedback.extend(plan_semantic_feedback(intent_plan, generated_sql))
                    attempt = max_attempts + 1
                if guarded is None or feedback:
                    logger.warning(
                        "query_generation_rejected route=%s attempts=%s feedback=%s sql=%s",
                        decision.route,
                        attempt,
                        feedback,
                        _redact_sql(generated_sql),
                    )
                    raise SQLGenerationError(
                        "Puchoo could not produce a safe, executable query for this request."
                    )
        else:
            attempt = 1
            generated_sql = client.generate_sql(schema=focused_schema, question=planned_question)
            guarded = executor.validate_query_plan(generated_sql)

        proposal = {
            "id": f"qry_{uuid4().hex[:12]}", 
            "workspace_id": workspace_id, 
            "question": question,
            "processing_question": planning_question,
            "language_code": language_code,
            "sql": guarded.sql, 
            "limit": guarded.limit, 
            "created_at": utc_now(),
            "model_attempts": attempt,
            "generation_method": "schema-guided fallback" if attempt == 0 or attempt > max_attempts else getattr(client, "provider_name", "local model"),
            "intent_plan": public_plan,
            "route": decision.route,
            "selected_tables": selected_tables,
            "assumptions": public_plan.get("assumptions", []),
            "interpreted_request": _translate_for_display(public_plan.get("normalized_question", planning_question), language_code),
            "status": "proposed"
        }
        trace = {
            "route": decision.route,
            "complexity_reasons": decision.reasons,
            "plan_valid": True,
            "plan": _plan_trace(public_plan),
            "selected_tables": selected_tables,
            "sql": _redact_sql(guarded.sql),
            "validation_outcome": "accepted",
            "retry_count": max(0, attempt - 1),
            "latency_ms": round((perf_counter() - started) * 1000),
        }
        proposal["pipeline_trace"] = trace
        _log_trace(trace)
        session_manager.active_proposals[workspace_id] = proposal
        return proposal
        
    except SQLGuardrailError as exc:
        blocked_record = {
            "id": f"qry_{uuid4().hex[:12]}", "workspace_id": workspace_id, "question": question,
            "language_code": language_code,
            "sql": "", "status": "blocked", "created_at": utc_now(), "row_count": 0, "rows": [], "elapsed_ms": 0,
            "verification": {"status": "BLOCKED", "summary": "Blocked before execution.", "details": str(exc)},
        }
        session_manager.query_history.setdefault(workspace_id, []).insert(0, blocked_record)
        session_manager.save(active_workspace_id=workspace_id)
        raise HTTPException(status_code=403, detail=f"Blocked for safety: {exc}")
        
    except (AnthropicConfigurationError, LocalMLXConfigurationError, QueryExecutionError, QueryPlanError, SQLGenerationError, ValueError) as exc:
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
        
        try:
            result = executor.execute(proposal["sql"])
        except QueryExecutionError as execution_error:
            client = get_sql_client()
            if not isinstance(client, LocalMLXSQLClient):
                raise
            schema = session_manager.schema_snapshots.get(f"schema_{workspace_id}") or get_schema_snapshot(
                workspace["database_uri"]
            )
            selected_schema = _schema_for_tables(schema, proposal.get("selected_tables", []))
            repair_question = (
                "Original question:\n" + proposal.get("processing_question", proposal["question"])
                + "\n\nStructured plan:\n"
                + json.dumps(proposal.get("intent_plan", {}), ensure_ascii=False, separators=(",", ":"))
            )
            repaired_sql = client.generate_sql(
                schema=selected_schema,
                question=repair_question,
                previous_sql=proposal["sql"],
                feedback=[f"Exact database error: {execution_error.database_error}"],
            )
            # Guard and database-plan the replacement before its single execution.
            guarded_repair = executor.validate_query_plan(repaired_sql)
            result = executor.execute(guarded_repair.sql)
            proposal["sql"] = guarded_repair.sql
            proposal["model_attempts"] = int(proposal.get("model_attempts", 1)) + 1
            repair_trace = proposal.setdefault("pipeline_trace", {})
            repair_trace["retry_count"] = int(
                proposal.get("pipeline_trace", {}).get("retry_count", 0)
            ) + 1
            repair_trace["sql"] = _redact_sql(guarded_repair.sql)
            repair_trace["validation_outcome"] = "accepted_after_runtime_repair"
            _log_trace(repair_trace)
        
        try:
            verification = get_verifier().verify(
                question=proposal.get("processing_question", proposal["question"]),
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
        from apps.core.result_presentation import build_result_presentation, humanize_column
        presentation = build_result_presentation(
            record.get("processing_question", record["question"]), record["columns"], record["rows"]
        )
        output_language = _spoken_language(record.get("language_code"))
        headline = _translate_for_display(presentation.headline, output_language)
        detail = _translate_for_display(presentation.detail, output_language)
        highlights = [
            (_translate_for_display(label, output_language), value)
            for label, value in presentation.highlights
        ]
        labels = {
            "executive_summary": _translate_for_display("Executive summary", output_language),
            "validated_answer": _translate_for_display("Validated against the returned data", output_language),
            "detailed_results": _translate_for_display("Detailed results", output_language),
            "rows_returned": _translate_for_display("rows returned", output_language),
            "no_rows": _translate_for_display("No rows returned.", output_language),
            "view_sql": _translate_for_display("View generated SQL", output_language),
            "read_only_query": _translate_for_display("Read-only query", output_language),
            "interpretation": _translate_for_display("How Pucho interpreted this request", output_language),
            "view_details": _translate_for_display("View details", output_language),
            "verified_match": _translate_for_display("Verified match", output_language),
            "needs_review": _translate_for_display("Needs review", output_language),
        }
        column_labels = {
            column: _translate_for_display(humanize_column(column), output_language)
            for column in record["columns"]
        }
        display_rows = _localize_rows(record["rows"], output_language)
        
        return {
            "record": record,
            "presentation": {
                "headline": headline,
                "detail": detail,
                "highlights": highlights,
                "language_code": output_language,
                "labels": labels,
                "column_labels": column_labels,
                "display_rows": display_rows,
            }
        }
        
    except (QueryExecutionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
