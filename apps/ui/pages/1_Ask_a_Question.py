from __future__ import annotations

import os
import sys
from html import escape
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.core.executor import QueryExecutionError, ReadOnlyExecutor
from apps.core.guardrails import SQLGuardrailError, validate_data_question
from apps.core.llm_client import (
    AnthropicConfigurationError,
    LocalMLXConfigurationError,
    LocalMLXSQLClient,
    SQLGenerationError,
    get_sql_client,
    get_local_sql_repair_client,
    local_semantic_feedback,
)
from apps.core.result_presentation import build_result_presentation, format_result_value, humanize_column, order_category_rows
from apps.core.schema_guided_queries import build_schema_guided_query
from apps.core.verification import ClaudeVerifier, VerificationStatus, verification_unavailable
from apps.core.workspaces import get_query_schema_context, get_schema_snapshot
from apps.ui.components.app_shell import add_history, initialize_app, page_header, require_workspace, utc_now, workspace_guardrails


def _format_date_value(value: object) -> str:
    """Show stored dates in a compact, readable form without changing source data."""

    parsed = pd.to_datetime(value, errors="coerce")
    return parsed.strftime("%d %b %Y") if not pd.isna(parsed) else str(value)


def _display_result_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Format result values without optional styling dependencies.

    The colour treatment for answer cards is CSS-based. Keeping the data grid
    as a plain dataframe avoids a rendering failure when a user's Python
    environment does not include optional visualization libraries.
    """

    display_frame = frame.rename(columns={column: humanize_column(column) for column in frame.columns})
    numeric_columns = list(display_frame.select_dtypes(include="number").columns)
    date_columns = [column for column in display_frame.columns if "date" in column.lower()]
    for column in numeric_columns:
        display_frame[column] = display_frame[column].map(format_result_value)
    for column in date_columns:
        display_frame[column] = display_frame[column].map(_format_date_value)
    return display_frame


initialize_app("Ask a Question")
st.markdown(
    """<style>
    .answer-hero { background:linear-gradient(120deg,#1d4ed8 0%,#7c3aed 55%,#db2777 100%); border-radius:18px; color:#fff; padding:1.35rem 1.5rem; box-shadow:0 12px 28px rgba(79,70,229,.20); }
    .answer-hero__label { font-size:.72rem; font-weight:800; letter-spacing:.09em; opacity:.83; text-transform:uppercase; }
    .answer-hero__title { font-size:1.7rem; font-weight:800; letter-spacing:-.035em; margin:.28rem 0 .3rem; }
    .answer-hero__detail { font-size:.95rem; line-height:1.5; opacity:.92; }
    .result-total { background:linear-gradient(120deg,#ecfdf5,#dbeafe); border:1px solid #a7f3d0; border-radius:14px; padding:1rem 1.15rem; margin:.2rem 0 .8rem; }
    .result-total__label { color:#166534; font-size:.75rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
    .result-total__value { color:#0f172a; font-size:1.65rem; font-weight:800; margin-top:.15rem; }
    .suggestion-card { border-radius:13px; padding:.9rem 1rem; min-height:98px; color:#172554; font-size:.9rem; font-weight:650; line-height:1.45; }
    .suggestion-card--one { background:#e0f2fe; border:1px solid #bae6fd; }
    .suggestion-card--two { background:#f3e8ff; border:1px solid #e9d5ff; }
    .suggestion-card--three { background:#dcfce7; border:1px solid #bbf7d0; }
    </style>""",
    unsafe_allow_html=True,
)
page_header(
    "Local English SQL pilot",
    "What would you like to know?",
    "The configured local SQL model answers automatically after read-only guardrails and database query-plan validation pass.",
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
    # A submitted question is always an independent request.  Do not let a
    # previous SQL statement, rows, or chat selection influence the generated
    # SQL or remain visible if this request is blocked or fails.
    st.session_state.active_proposal = None
    st.session_state.last_execution = None
    st.session_state.chat_context = None
    try:
        schema = get_schema_snapshot(workspace["database_uri"])
        validate_data_question(question.strip(), schema)
        executor = ReadOnlyExecutor(workspace["database_uri"], max_rows=controls["max_rows"], dialect=workspace.get("dialect", "sqlite"), timeout_seconds=controls["timeout_seconds"])
        client = get_sql_client()
        repair_client = get_local_sql_repair_client() if isinstance(client, LocalMLXSQLClient) else None
        generated_sql = build_schema_guided_query(
            workspace["database_uri"], question.strip(), dialect=workspace.get("dialect", "sqlite")
        )
        guarded = None
        generation_method = "schema-guided query"
        attempt = 0
        if generated_sql:
            try:
                guarded = executor.validate_query_plan(generated_sql)
            except (SQLGuardrailError, QueryExecutionError):
                # A narrow route is only a convenience. Fall back to model
                # generation if this uploaded schema cannot satisfy it.
                generated_sql = ""

        if guarded is None:
            model_schema = schema
            if isinstance(client, LocalMLXSQLClient):
                # This focused inspection is local, bounded, and synchronous.
                # Do not put optional vector retrieval on the interactive path:
                # a stalled embedding/index service must never leave the user
                # waiting before the SQL model is even contacted.
                model_schema = get_query_schema_context(workspace["database_uri"], question.strip())
            generation_method = (
                "primary local model + local repair model"
                if repair_client is not None
                else "local model"
            ) if isinstance(client, LocalMLXSQLClient) else "Claude model"

        if guarded is None and isinstance(client, LocalMLXSQLClient):
            try:
                # One attempt rarely gives a small local model enough feedback
                # for multi-table questions. Cap retries to keep the UI
                # responsive while allowing syntax and join repair.
                max_attempts = max(1, min(int(os.getenv("LOCAL_SQL_MAX_ATTEMPTS", "3")), 5))
            except ValueError:
                max_attempts = 3
            feedback: list[str] | None = None
            previous_sql: str | None = None
            generated_sql = ""
            for attempt in range(1, max_attempts + 1):
                attempt_client = repair_client if repair_client is not None and feedback else client
                try:
                    generated_sql = attempt_client.generate_sql(
                        schema=model_schema,
                        question=question.strip(),
                        feedback=feedback,
                        previous_sql=previous_sql,
                    )
                except LocalMLXConfigurationError:
                    if attempt_client is client:
                        raise
                    # The primary model remains usable when the optional repair
                    # server is stopped or still loading.
                    generated_sql = client.generate_sql(
                        schema=model_schema,
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
        elif guarded is None:
            generated_sql = client.generate_sql(
                schema=model_schema,
                question=question.strip(),
            )
            guarded = executor.validate_query_plan(generated_sql)
        st.session_state.active_proposal = {
            "id": f"qry_{uuid4().hex[:12]}", "workspace_id": workspace["id"], "question": question.strip(),
            "sql": guarded.sql, "limit": guarded.limit, "created_at": utc_now(),
            "model_attempts": attempt if isinstance(client, LocalMLXSQLClient) else 1,
            "generation_method": generation_method,
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
# Do not render a successful prior answer below a failed or edited question.
# That can look as though the assistant ignored the text currently in the box.
if (
    record
    and record.get("workspace_id") == workspace["id"]
    and record.get("question") == question.strip()
):
    st.divider()
    presentation = build_result_presentation(record["question"], record["columns"], record["rows"])
    st.subheader("Answer")
    st.markdown(
        f'<div class="answer-hero"><div class="answer-hero__label">Validated result</div>'
        f'<div class="answer-hero__title">{escape(presentation.headline)}</div>'
        f'<div class="answer-hero__detail">{escape(presentation.detail)}</div></div>',
        unsafe_allow_html=True,
    )
    if presentation.highlights:
        metrics = st.columns(len(presentation.highlights))
        for metric, (label, value) in zip(metrics, presentation.highlights):
            metric.metric(label, value)

    st.subheader(presentation.breakdown_title or "Detailed results")
    st.caption(f"{record['row_count']} rows · {record['elapsed_ms']} ms · query limited before execution")
    if record["rows"]:
        display_rows = order_category_rows(record["question"], record["rows"], presentation.category_column)
        frame = pd.DataFrame(display_rows)
        try:
            st.dataframe(_display_result_table(frame), width="stretch", hide_index=True)
        except Exception:
            # A database value with an unfamiliar display type should never
            # hide a successfully retrieved answer from the user.
            st.dataframe(frame, width="stretch", hide_index=True)
        if presentation.total:
            st.subheader("Total")
            total_label, total_value = presentation.total
            st.markdown(
                f'<div class="result-total"><div class="result-total__label">{escape(total_label)}</div>'
                f'<div class="result-total__value">{escape(total_value)}</div></div>',
                unsafe_allow_html=True,
            )
        st.download_button("Download CSV", data=frame.to_csv(index=False).encode("utf-8"), file_name="puchoo-query-results.csv", mime="text/csv")
    else:
        st.info("The query ran successfully and returned no rows.")

    if presentation.recommendations:
        st.subheader("Helpful next questions")
        suggestion_columns = st.columns(len(presentation.recommendations))
        style_names = ["one", "two", "three"]
        for column, recommendation, style_name in zip(suggestion_columns, presentation.recommendations, style_names):
            with column:
                st.markdown(f'<div class="suggestion-card suggestion-card--{style_name}">{escape(recommendation)}</div>', unsafe_allow_html=True)

    with st.expander("How this answer was retrieved"):
        st.caption(
            f"One validated read-only SELECT · result limit {record['limit']:,} · "
            f"{record.get('generation_method', 'local model')} · "
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
