from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.core.executor import QueryExecutionError, ReadOnlyExecutor
from apps.core.guardrails import SQLGuardrailError
from apps.core.llm_client import (
    AnthropicConfigurationError,
    LocalMLXConfigurationError,
    LocalMLXSQLClient,
    SQLGenerationError,
    get_sql_client,
    local_semantic_feedback,
)
from apps.core.result_presentation import build_result_presentation
from apps.core.verification import ClaudeVerifier, VerificationStatus, verification_unavailable
from apps.core.workspaces import get_schema_snapshot
from apps.ui.components.app_shell import add_history, initialize_app, page_header, require_workspace, utc_now, workspace_guardrails


initialize_app("Ask a Question")
page_header(
    "Local English SQL pilot",
    "What would you like to know?",
    "The local Qwen Coder model answers automatically after read-only guardrails and database query-plan validation pass.",
)
workspace = require_workspace()
if workspace is None:
    st.stop()

controls = workspace_guardrails(workspace["id"])
with st.container(border=True):
    st.markdown("<span class='small-label'>YOUR QUESTION</span>", unsafe_allow_html=True)
    st.caption("English text only for this local-model pilot. Voice and translation will be added in a later Sarvam phase.")
    question = st.text_area("Your question", placeholder="Ask a question about this workspace's data…", height=104, key="question_input", label_visibility="collapsed")
    question_actions = st.columns((1, 2))
    with question_actions[0]:
        st.caption(f"Read-only enforced · up to {controls['max_rows']:,} rows")
    with question_actions[1]:
        generate_clicked = st.button("Generate answer", type="primary", disabled=not question.strip(), use_container_width=True)
proposal = st.session_state.active_proposal
if proposal and (proposal["workspace_id"] != workspace["id"] or proposal["question"] != question.strip()):
    st.session_state.active_proposal = None
    proposal = None

if generate_clicked:
    try:
        schema = get_schema_snapshot(workspace["database_uri"])
        executor = ReadOnlyExecutor(workspace["database_uri"], max_rows=controls["max_rows"], dialect=workspace.get("dialect", "sqlite"), timeout_seconds=controls["timeout_seconds"])
        client = get_sql_client()
        if isinstance(client, LocalMLXSQLClient):
            try:
                max_attempts = max(1, min(int(os.getenv("LOCAL_SQL_MAX_ATTEMPTS", "3")), 3))
            except ValueError:
                max_attempts = 3
            feedback: list[str] | None = None
            previous_sql: str | None = None
            guarded = None
            generated_sql = ""
            for attempt in range(1, max_attempts + 1):
                generated_sql = client.generate_sql(
                    schema=schema,
                    question=question.strip(),
                    feedback=feedback,
                    previous_sql=previous_sql,
                )
                feedback = local_semantic_feedback(question.strip(), generated_sql)
                try:
                    guarded = executor.validate_query_plan(generated_sql)
                except (SQLGuardrailError, QueryExecutionError) as exc:
                    feedback.insert(0, str(exc))
                if not feedback:
                    break
                previous_sql = generated_sql
            if guarded is None or feedback:
                raise SQLGenerationError(
                    "The local model could not produce a safe, executable query after repair attempts. "
                    "Try rephrasing the question."
                )
        else:
            generated_sql = client.generate_sql(schema=schema, question=question.strip())
            guarded = executor.validate_query_plan(generated_sql)
        st.session_state.active_proposal = {
            "id": f"qry_{uuid4().hex[:12]}", "workspace_id": workspace["id"], "question": question.strip(),
            "sql": guarded.sql, "limit": guarded.limit, "created_at": utc_now(),
            "model_attempts": attempt if isinstance(client, LocalMLXSQLClient) else 1,
        }
        proposal = st.session_state.active_proposal
        result = executor.execute(proposal["sql"])
        try:
            verification = ClaudeVerifier().verify(
                question=proposal["question"],
                sql=result.sql,
                columns=result.columns,
                rows=result.rows,
                row_count=result.row_count,
            )
        except RuntimeError as exc:
            verification = verification_unavailable(str(exc))
        record = {
            **proposal,
            "status": "executed",
            "sql": result.sql,
            "row_count": result.row_count,
            "rows": result.rows,
            "columns": result.columns,
            "elapsed_ms": result.elapsed_ms,
            "verification": verification.as_dict(),
            "created_at": utc_now(),
        }
        add_history(workspace["id"], record)
        st.session_state.active_proposal = None
        st.session_state.last_execution = record
        st.rerun()
    except SQLGuardrailError as exc:
        add_history(workspace["id"], {
            "id": f"qry_{uuid4().hex[:12]}", "workspace_id": workspace["id"], "question": question.strip(),
            "sql": "", "status": "blocked", "created_at": utc_now(), "row_count": 0, "rows": [], "elapsed_ms": 0,
            "verification": {"status": "BLOCKED", "summary": "Blocked before execution.", "details": str(exc)},
        })
        st.error(f"Blocked for safety: {exc}")
    except (AnthropicConfigurationError, LocalMLXConfigurationError, QueryExecutionError, SQLGenerationError, ValueError) as exc:
        st.error(str(exc))

record = st.session_state.get("last_execution")
if record and record.get("workspace_id") == workspace["id"]:
    st.divider()
    presentation = build_result_presentation(record["question"], record["columns"], record["rows"])
    st.subheader("Answer")
    with st.container(border=True):
        st.markdown(f"### {presentation.headline}")
        st.caption(presentation.detail)
        if presentation.highlights:
            metrics = st.columns(len(presentation.highlights))
            for metric, (label, value) in zip(metrics, presentation.highlights):
                metric.metric(label, value)

    st.subheader("Detailed results")
    st.caption(f"{record['row_count']} rows · {record['elapsed_ms']} ms · query limited before execution")
    if record["rows"]:
        frame = pd.DataFrame(record["rows"])
        st.dataframe(frame, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", data=frame.to_csv(index=False).encode("utf-8"), file_name="puchoo-query-results.csv", mime="text/csv")
    else:
        st.info("The query ran successfully and returned no rows.")

    with st.expander("How this answer was retrieved"):
        st.caption(
            f"One validated read-only SELECT · result limit {record['limit']:,} · "
            f"local-model attempts {record.get('model_attempts', 1)}"
        )
        st.code(record["sql"], language="sql")

    verification = record["verification"]
    status = verification["status"]
    st.subheader("Independent verification")
    if status == VerificationStatus.VERIFIED.value:
        st.success(f"Verified · {verification.get('confidence', 0)}% confidence — {verification['summary']}")
    elif status == VerificationStatus.VERIFICATION_MISMATCH.value:
        st.error(f"VERIFICATION MISMATCH · {verification.get('confidence', 0)}% confidence — {verification['summary']}")
        st.warning("Treat this answer as untrusted and inspect the SQL and rows before acting on it.")
    else:
        st.warning("Verification unavailable — the query result is shown, but has not been independently checked.")
        if verification.get("details"):
            st.caption(verification["details"])

    st.caption("English-only pilot · Sarvam voice and translation are intentionally disabled.")
