from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.core.workspaces import get_schema_metrics
from apps.ui.components.app_shell import initialize_app, page_header, persist_app_state, require_workspace, workspace_guardrails


initialize_app("Guardrails")
page_header("Settings & safety", "Settings", "Manage your local profile, connected workspace, and the read-only controls enforced at the database execution boundary.")
workspace = require_workspace()
if workspace is None:
    st.stop()

current = workspace_guardrails(workspace["id"])
profile = st.session_state.profile
with st.container(border=True):
    st.subheader("Profile")
    st.caption("Saved locally on this machine until authentication is connected.")
    with st.form("profile_settings", border=False):
        left, right = st.columns(2)
        with left:
            name = st.text_input("Full name", value=profile["name"])
            department = st.text_input("Department / workspace", value=profile["department"])
        with right:
            email = st.text_input("Email address", value=profile["email"])
            timezone = st.text_input("Timezone", value=profile["timezone"])
        save_profile = st.form_submit_button("Save profile", type="primary")
    if save_profile:
        st.session_state.profile = {"name": name.strip(), "email": email.strip(), "department": department.strip(), "timezone": timezone.strip()}
        persist_app_state()
        st.success("Profile saved locally.")

st.write("")
with st.container(border=True):
    st.subheader("Connected database")
    try:
        metrics = get_schema_metrics(workspace["database_uri"])
        metrics_columns = st.columns(3)
        for column, label, value in zip(metrics_columns, ("Workspace", "Tables indexed", "Columns available"), (workspace["name"], metrics["tables"], metrics["columns"])):
            with column:
                value_class = "workspace-value" if label == "Workspace" else "metric-value"
                st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="{value_class}">{escape(str(value))}</div></div>', unsafe_allow_html=True)
    except ValueError as exc:
        st.error(str(exc))

st.write("")
with st.container(border=True):
    st.subheader("Safety & guardrails")
    st.caption("Read-only SQL is system-enforced and cannot be disabled.")
    with st.form("guardrail_settings", border=False):
        max_rows = st.number_input("Automatic row limit", min_value=1, max_value=10_000, value=int(current["max_rows"]), step=50)
        timeout = st.number_input("Timeout cap (seconds)", min_value=1, max_value=120, value=int(current["timeout_seconds"]), step=1)
        confirm_complex = st.checkbox("Require confirmation for complex queries", value=bool(current["confirm_complex_queries"]))
        st.caption("Always on: one statement only · SELECT only · data-changing CTEs rejected · outer result limit clamped.")
        saved = st.form_submit_button("Save safety controls", type="primary")
    if saved:
        st.session_state.workspace_guardrails[workspace["id"]] = {"max_rows": int(max_rows), "timeout_seconds": int(timeout), "confirm_complex_queries": confirm_complex}
        persist_app_state()
        st.success("Safety controls saved for this workspace.")

st.write("")
with st.container(border=True):
    st.subheader("Local history")
    st.caption("Query history is saved locally for this workspace and remains available after browser refresh.")
    clear_confirmed = st.checkbox("I understand this clears the locally saved history for the active workspace.", key="clear_history_confirm")
    if st.button("Clear query history", disabled=not clear_confirmed):
        st.session_state.query_history[workspace["id"]] = []
        st.session_state.active_proposal = None
        st.session_state.pop("last_execution", None)
        persist_app_state()
        st.success("Local query history cleared for this workspace.")
