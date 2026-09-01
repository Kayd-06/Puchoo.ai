"""Session-local query history for the Streamlit MVP."""

from __future__ import annotations

from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import pandas as pd
import streamlit as st

from components.app_shell import badge, configure_page, format_timestamp, set_feedback
from data.demo_data import results_frame


configure_page("Query history", "🕘")

st.markdown('<div class="pucho-eyebrow">Auditable activity</div>', unsafe_allow_html=True)
st.title("Query history")
st.caption("Review questions, guardrail decisions, and the results you chose to run in this session.")

history = st.session_state.query_history
filter_search, filter_status = st.columns([2, .75])
with filter_search:
    search = st.text_input("Search questions", placeholder="Search by question or SQL…", label_visibility="collapsed")
with filter_status:
    status = st.selectbox("Status", ["All activity", "Awaiting approval", "Executed", "Blocked"], label_visibility="collapsed")

filtered = []
for item in history:
    searchable = f"{item['question']} {item['sql']}".lower()
    requested_status = {"Awaiting approval": "approved"}.get(status, status.lower())
    status_matches = status == "All activity" or item["status"] == requested_status
    if (not search or search.lower() in searchable) and status_matches:
        filtered.append(item)

if not filtered:
    st.info("No queries match those filters. Try a broader search or ask a new question.")
    st.page_link("pages/1_Ask_a_Question.py", label="Ask a question", icon="💬")
    st.stop()

table_rows = [
    {
        "Question": item["question"],
        "Status": "Awaiting approval" if item["status"] == "approved" else item["status"].title(),
        "Rows": str(len(item["rows"])) if item["executed"] else "—",
        "Duration": f"{item['execution_ms']} ms" if item["execution_ms"] else "—",
        "When": format_timestamp(item.get("executed_at") or item.get("generated_at")),
    }
    for item in filtered
]
st.dataframe(pd.DataFrame(table_rows), width="stretch", hide_index=True)


def describe_choice(item: dict[str, object]) -> str:
    return f"{item['question']} · {format_timestamp(item.get('executed_at') or item.get('generated_at'))}"


selected = st.selectbox(
    "Inspect an activity item",
    filtered,
    format_func=describe_choice,
    label_visibility="collapsed",
)

st.markdown('<hr class="pucho-rule">', unsafe_allow_html=True)
heading, tag = st.columns([1.4, .6], vertical_alignment="center")
with heading:
    st.markdown("### Query detail")
    st.write(selected["question"])
with tag:
    if selected["status"] == "executed":
        badge("Executed", "success")
    elif selected["status"] == "blocked":
        badge("Blocked", "warning")
    else:
        badge("Awaiting approval", "neutral")

if selected["status"] == "blocked":
    st.error(selected["guardrail_message"])
    st.code(selected["sql"], language="sql")
    st.caption("Blocked statements are retained here for auditability and are never executed.")
    st.stop()

st.info(selected["guardrail_message"], icon="🛡️")
st.caption(selected["explanation"])
with st.expander("Generated SQL", expanded=False):
    st.code(selected["sql"], language="sql")

if selected["executed"]:
    result_frame = results_frame(selected)
    st.dataframe(result_frame, width="stretch", hide_index=True)
    st.caption(selected["result_summary"])

feedback_col, reload_col = st.columns([1, 1])
with feedback_col:
    st.caption("Was this query useful?")
    yes, no = st.columns(2)
    with yes:
        st.button("👍 Yes", key=f"history_up_{selected['id']}", width="stretch", on_click=set_feedback, args=(selected["id"], "up"))
    with no:
        st.button("👎 No", key=f"history_down_{selected['id']}", width="stretch", on_click=set_feedback, args=(selected["id"], "down"))
with reload_col:
    st.caption("Want to refine this answer?")
    if st.button("Load question into Ask", width="stretch"):
        st.session_state.draft_question = selected["question"]
        st.session_state.generated_query = None
        st.switch_page("pages/1_Ask_a_Question.py")
