from __future__ import annotations

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
from apps.core.llm_client import AnthropicConfigurationError, LLMClient, SQLGenerationError
from apps.core.sarvam_client import SarvamClient, SarvamConfigurationError
from apps.core.verification import ClaudeVerifier, VerificationStatus, verification_unavailable
from apps.core.workspaces import get_schema_snapshot
from apps.ui.components.app_shell import add_history, initialize_app, page_header, require_workspace, utc_now, workspace_guardrails


LANGUAGES = {
    "Hindi": "hi-IN", "Bengali": "bn-IN", "Gujarati": "gu-IN", "Kannada": "kn-IN",
    "Malayalam": "ml-IN", "Marathi": "mr-IN", "Odia": "od-IN", "Punjabi": "pa-IN",
    "Tamil": "ta-IN", "Telugu": "te-IN", "Assamese": "as-IN", "Bodo": "brx-IN",
    "Dogri": "doi-IN", "Konkani": "kok-IN", "Kashmiri": "ks-IN", "Maithili": "mai-IN",
    "Manipuri": "mni-IN", "Nepali": "ne-IN", "Sanskrit": "sa-IN", "Santali": "sat-IN",
    "Sindhi": "sd-IN", "Urdu": "ur-IN",
}
TRANSLITERATION_LANGUAGES = {name: code for name, code in LANGUAGES.items() if code in {
    "hi-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN",
}}


initialize_app("Ask a Question")
page_header("Deterministic natural-SQL engine", "What would you like to know?", "Ask in plain English. Claude Sonnet 5 proposes a read-only query; guardrails validate it before you can approve execution.")
workspace = require_workspace()
if workspace is None:
    st.stop()

controls = workspace_guardrails(workspace["id"])
with st.container(border=True):
    if st.session_state.get("pending_voice_question"):
        st.session_state.question_input = st.session_state.pop("pending_voice_question")
    question_label, voice_action = st.columns((6, 1))
    with question_label:
        st.markdown("<span class='small-label'>YOUR QUESTION</span>", unsafe_allow_html=True)
    with voice_action:
        with st.popover("🎙 Voice", use_container_width=True):
            st.caption("Record in an Indian language. Sarvam transcribes it before SQL generation.")
            voice_question = st.audio_input("Voice question", sample_rate=16_000, label_visibility="collapsed")
            if voice_question and st.button("Transcribe", type="primary", use_container_width=True):
                try:
                    transcript = SarvamClient().transcribe(voice_question.getvalue(), voice_question.name)
                    st.session_state.pending_voice_question = transcript
                    st.rerun()
                except SarvamConfigurationError:
                    st.info("Add SARVAM_API_KEY to .env to enable voice transcription.")
                except (RuntimeError, ValueError) as exc:
                    st.error(str(exc))
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
        generated_sql = LLMClient().generate_sql(schema=schema, question=question.strip())
        guarded = executor.prepare(generated_sql)
        st.session_state.active_proposal = {
            "id": f"qry_{uuid4().hex[:12]}", "workspace_id": workspace["id"], "question": question.strip(),
            "sql": guarded.sql, "limit": guarded.limit, "created_at": utc_now(),
            "requires_complex_confirmation": controls["confirm_complex_queries"] and executor.guardrails.requires_confirmation(guarded.sql),
        }
        proposal = st.session_state.active_proposal
    except SQLGuardrailError as exc:
        add_history(workspace["id"], {
            "id": f"qry_{uuid4().hex[:12]}", "workspace_id": workspace["id"], "question": question.strip(),
            "sql": "", "status": "blocked", "created_at": utc_now(), "row_count": 0, "rows": [], "elapsed_ms": 0,
            "verification": {"status": "BLOCKED", "summary": "Blocked before execution.", "details": str(exc)},
        })
        st.error(f"Blocked for safety: {exc}")
    except (AnthropicConfigurationError, SQLGenerationError, ValueError) as exc:
        st.error(str(exc))

proposal = st.session_state.active_proposal
if proposal:
    st.divider()
    st.markdown("<span class='status status-ok'>GUARDRAILS PASSED</span>", unsafe_allow_html=True)
    st.caption(f"One read-only SELECT · result limit {proposal['limit']:,} · generated for this exact question")
    st.code(proposal["sql"], language="sql")
    st.warning("Review the SQL before running it. This is the approval boundary.")
    complex_confirmed = True
    if proposal.get("requires_complex_confirmation"):
        complex_confirmed = st.checkbox("I reviewed this complex query and approve execution.", key=f"complex_{proposal['id']}")
        if not complex_confirmed:
            st.caption("This proposal includes joins or nested selects, so a second confirmation is required.")
    if st.button("Run approved query", type="primary", disabled=not complex_confirmed):
        try:
            executor = ReadOnlyExecutor(workspace["database_uri"], max_rows=controls["max_rows"], dialect=workspace.get("dialect", "sqlite"), timeout_seconds=controls["timeout_seconds"])
            result = executor.execute(proposal["sql"])
            try:
                verification = ClaudeVerifier().verify(question=proposal["question"], sql=result.sql, columns=result.columns, rows=result.rows, row_count=result.row_count)
            except RuntimeError as exc:
                verification = verification_unavailable(str(exc))
            record = {
                **proposal, "status": "executed", "sql": result.sql, "row_count": result.row_count,
                "rows": result.rows, "columns": result.columns, "elapsed_ms": result.elapsed_ms,
                "verification": verification.as_dict(), "created_at": utc_now(),
            }
            add_history(workspace["id"], record)
            st.session_state.active_proposal = None
            st.session_state.last_execution = record
            st.rerun()
        except (QueryExecutionError, SQLGuardrailError) as exc:
            st.error(str(exc))

record = st.session_state.get("last_execution")
if record and record.get("workspace_id") == workspace["id"]:
    st.divider()
    st.subheader("Execution result")
    st.caption(f"{record['row_count']} rows · {record['elapsed_ms']} ms · query limited before execution")
    if record["rows"]:
        frame = pd.DataFrame(record["rows"])
        st.dataframe(frame, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", data=frame.to_csv(index=False).encode("utf-8"), file_name="puchoo-query-results.csv", mime="text/csv")
    else:
        st.info("The query ran successfully and returned no rows.")

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

    st.subheader("Regional-language output")
    output_mode = st.radio("Output style", ("Translate meaning", "Transliterate pronunciation"), horizontal=True)
    language_options = LANGUAGES if output_mode == "Translate meaning" else TRANSLITERATION_LANGUAGES
    language_name = st.selectbox("Answer language", list(language_options), key=f"answer_language_{output_mode}")
    if st.button("Convert verification summary"):
        try:
            client = SarvamClient()
            converter = client.translate if output_mode == "Translate meaning" else client.transliterate
            record["localized_summary"] = {
                "language": language_name,
                "mode": output_mode,
                "text": converter(verification["summary"], language_options[language_name]),
            }
            st.rerun()
        except (SarvamConfigurationError, RuntimeError, ValueError) as exc:
            st.error(str(exc))
    localized = record.get("localized_summary")
    if localized:
        st.caption(f"{localized['language']} · {localized['mode']}")
        st.info(localized["text"])
