"""Visible, user-facing safety settings for the Streamlit MVP."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from components.app_shell import badge, configure_page
from data.demo_data import DEFAULT_GUARDRAILS


configure_page("Guardrail settings", "🛡️")

st.markdown('<div class="pucho-eyebrow">Safety controls</div>', unsafe_allow_html=True)
st.title("Guardrail settings")
st.caption("This standalone demo previews policy. A production FastAPI and execution service must enforce every setting server-side.")

settings = st.session_state.guardrail_settings

st.markdown("### Query limits")
limits_left, limits_right = st.columns(2)
with limits_left:
    max_rows = st.number_input(
        "Maximum returned rows",
        min_value=10,
        max_value=10_000,
        value=int(settings["max_rows"]),
        step=10,
        help="The demo adds LIMIT to its SQL preview. The execution service must enforce the cap in production.",
    )
with limits_right:
    timeout = st.number_input(
        "Query timeout (seconds)",
        min_value=5,
        max_value=120,
        value=int(settings["timeout_seconds"]),
        step=5,
        help="Stored as a demo preference; the future execution service must enforce it.",
    )

schema = st.selectbox(
    "Allowed schema",
    options=["main"],
    index=0,
    help="A production connection API will supply and enforce the allowed schema scope.",
)

save, reset = st.columns([.45, .55])
with save:
    if st.button("Save demo preferences", type="primary", width="stretch"):
        st.session_state.guardrail_settings.update(
            {"max_rows": int(max_rows), "timeout_seconds": int(timeout), "allowed_schema": schema}
        )
        st.success("Demo preferences saved for this local session.")
with reset:
    if st.button("Reset defaults", width="stretch"):
        st.session_state.guardrail_settings = deepcopy(DEFAULT_GUARDRAILS)
        st.rerun()

st.markdown('<hr class="pucho-rule">', unsafe_allow_html=True)
st.markdown("### Required production protections")
st.caption("These are non-negotiable policies for the API and execution services. This UI demo does not validate or execute database SQL.")

rules = [
    ("Write operations", "UPDATE, DELETE, INSERT, DROP, ALTER, and other data-changing statements are blocked.", "block_writes"),
    ("Single statement only", "Multiple statements and comment-based bypass attempts are rejected before execution.", "block_multiple_statements"),
    ("Complexity checks", "Queries with unsafe structures or excessive work are blocked or sent back for revision.", "enforce_complexity_checks"),
]
for title, description, key in rules:
    card, indicator = st.columns([4, 1], vertical_alignment="center")
    with card:
        st.markdown(f"<div class='pucho-card'><h3>{title}</h3><div class='pucho-small'>{description}</div></div>", unsafe_allow_html=True)
    with indicator:
        st.toggle(title, value=bool(settings[key]), disabled=True, key=f"display_{key}")

st.markdown('<hr class="pucho-rule">', unsafe_allow_html=True)
st.markdown("### Production Pucho will never run")
never_left, never_right = st.columns(2)
with never_left:
    badge("No data-modifying SQL", "success")
    st.caption("The execution service must reject data-changing SQL. This demo has no database connection.")
with never_right:
    badge("No unreviewed query execution", "success")
    st.caption("A production API must require explicit approval and revalidate the SQL before execution.")
