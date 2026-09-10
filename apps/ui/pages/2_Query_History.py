from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.ui.components.app_shell import history_for, initialize_app, page_header, require_workspace


initialize_app("Query History")
page_header("Audit & traceability", "Query history", "Review real questions and their evidence. History is isolated to the active workspace and contains only your executed or blocked queries.")
workspace = require_workspace()
if workspace is None:
    st.stop()

history = history_for(workspace["id"])
if not history:
    with st.container(border=True):
        st.markdown("<span class='status status-warn'>NO ACTIVITY YET</span>", unsafe_allow_html=True)
        st.subheader("Your verified query trail will appear here")
        st.write("Ask a question, review the generated SQL, and approve execution. This page will retain the resulting audit record after browser refresh.")
        if st.button("Ask data", type="primary"):
            st.switch_page("pages/1_Ask_a_Question.py")
    st.stop()

def verification_status(item: dict[str, object]) -> str:
    verification = item.get("verification", {})
    return str(verification.get("status", item.get("status", "")) if isinstance(verification, dict) else item.get("status", ""))


verified_count = sum(verification_status(item) == "VERIFIED" for item in history)
review_count = sum(verification_status(item) == "VERIFICATION_MISMATCH" for item in history)
blocked_count = sum(verification_status(item).upper() == "BLOCKED" for item in history)
metrics = st.columns(3)
for column, label, value in zip(metrics, ("Verified", "Needs review", "Blocked"), (verified_count, review_count, blocked_count)):
    with column:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div></div>", unsafe_allow_html=True)

st.write("")
search = st.text_input("Search questions, SQL, or verification summaries", placeholder="Search this workspace's activity…")
filter_columns = st.columns(4)
statuses = ("All", "Verified", "Needs review", "Blocked")
chosen = "All"
for column, label in zip(filter_columns, statuses):
    with column:
        if st.button(label, key=f"history_filter_{label}", use_container_width=True, type="primary" if st.session_state.get("history_filter", "All") == label else "secondary"):
            st.session_state.history_filter = label
chosen = st.session_state.get("history_filter", "All")

def matches(item: dict[str, object]) -> bool:
    status = verification_status(item)
    if chosen == "Verified" and status != "VERIFIED":
        return False
    if chosen == "Needs review" and status != "VERIFICATION_MISMATCH":
        return False
    if chosen == "Blocked" and status.upper() != "BLOCKED":
        return False
    verification = item.get("verification", {})
    summary = verification.get("summary", "") if isinstance(verification, dict) else ""
    corpus = " ".join(str(item.get(field, "")) for field in ("question", "sql")) + str(summary)
    return not search.strip() or search.casefold() in corpus.casefold()

filtered_history = [item for item in history if matches(item)]
if not filtered_history:
    st.info("No activity matches the current filters.")

for item in filtered_history:
    verification = item.get("verification", {})
    status = verification_status(item)
    style = "status-ok" if status == "VERIFIED" else "status-bad" if status.upper() == "BLOCKED" else "status-warn"
    with st.container(border=True):
        left, right = st.columns((5, 1))
        with left:
            st.subheader(str(item["question"]))
            st.caption(f"{item.get('created_at', '').replace('T', ' ')[:19]} · {item.get('row_count', 0)} rows returned · {item.get('elapsed_ms', 0)} ms")
        with right:
            st.markdown(f"<span class='status {style}'>{status.replace('_', ' ')}</span>", unsafe_allow_html=True)
        if verification:
            st.write(verification.get("summary", ""))
            if verification.get("details"):
                st.caption(verification["details"])
        if item.get("sql"):
            with st.expander("View guarded SQL"):
                st.code(item["sql"], language="sql")
        if item.get("rows"):
            with st.expander("View returned rows"):
                st.dataframe(item["rows"], use_container_width=True, hide_index=True)
