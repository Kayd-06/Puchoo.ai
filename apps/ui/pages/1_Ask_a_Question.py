"""The review-before-run natural-language query workflow."""

from __future__ import annotations

from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from components.app_shell import (
    badge,
    clear_query_draft,
    configure_page,
    set_feedback,
    upsert_history,
)
from data.demo_data import execute_demo_query, generate_demo_query, results_frame


configure_page("Ask a question", "💬")


def use_example(question: str) -> None:
    st.session_state.draft_question = question
    st.session_state.generated_query = None


def invalidate_query_on_question_change() -> None:
    """Prevent approval of a SQL proposal after its source question changes."""
    current = st.session_state.generated_query
    if current and current["question"] != st.session_state.draft_question.strip():
        st.session_state.generated_query = None


def generate_query() -> None:
    question = st.session_state.draft_question.strip()
    if not question:
        st.session_state.question_error = "Write a question before generating a query."
        return
    st.session_state.question_error = None
    max_rows = st.session_state.guardrail_settings["max_rows"]
    proposal = generate_demo_query(question, max_rows)
    st.session_state.generated_query = proposal
    upsert_history(proposal)


def run_approved_query() -> None:
    current = st.session_state.generated_query
    if current is None or current["status"] != "approved":
        return
    if current["question"] != st.session_state.draft_question.strip():
        st.session_state.generated_query = None
        st.session_state.question_error = "Your question changed. Generate a new SQL proposal before running it."
        return
    executed = execute_demo_query(current)
    st.session_state.generated_query = executed
    upsert_history(executed)


section_left, section_right = st.columns([1.45, 1], vertical_alignment="bottom")
with section_left:
    st.markdown('<div class="pucho-eyebrow">Query workspace</div>', unsafe_allow_html=True)
    st.title("Ask a question")
    st.caption("Describe what you need. Pucho will draft SQL but will not execute it without your approval.")
with section_right:
    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
    badge(f"Demo preview · {st.session_state.guardrail_settings['max_rows']:,}-row limit", "info")

st.markdown("#### What would you like to know?")
st.text_area(
    "Question",
    key="draft_question",
    on_change=invalidate_query_on_question_change,
    label_visibility="collapsed",
    height=128,
    placeholder="For example: Which regions had the highest completed-order revenue this quarter?",
)

if st.session_state.get("question_error"):
    st.error(st.session_state.question_error)

example_one, example_two, example_three, action = st.columns([1, 1.15, 1.1, .8])
with example_one:
    st.button(
        "Monthly revenue",
        width="stretch",
        on_click=use_example,
        args=("How has monthly revenue changed over the last six months?",),
    )
with example_two:
    st.button(
        "Customer value",
        width="stretch",
        on_click=use_example,
        args=("Which customer segments have the highest lifetime value?",),
    )
with example_three:
    st.button(
        "Revenue by region",
        width="stretch",
        on_click=use_example,
        args=("Which regions generated the most completed-order revenue?",),
    )
with action:
    st.button("Generate SQL", type="primary", width="stretch", on_click=generate_query)

with st.expander("Query options", expanded=False):
    option_a, option_b = st.columns(2)
    with option_a:
        st.caption(f"The SQL preview includes a **{st.session_state.guardrail_settings['max_rows']:,}-row LIMIT**.")
    with option_b:
        st.caption("This UI uses a fictitious schema and never connects to a database.")

query = st.session_state.generated_query
if query is None:
    st.markdown('<hr class="pucho-rule">', unsafe_allow_html=True)
    st.info("Start with a question to see a proposed SQL query, explanation, and guardrail review.", icon="💡")
    st.stop()

st.markdown('<hr class="pucho-rule">', unsafe_allow_html=True)
review_title, review_action = st.columns([1, .42], vertical_alignment="center")
with review_title:
    st.markdown("### Query review")
    st.caption(f"Question under review: {query['question']}")
with review_action:
    st.button("Start over", width="stretch", on_click=clear_query_draft)

if query["status"] == "blocked":
    badge("Blocked by guardrails", "warning")
    st.error(query["guardrail_message"])
    st.stop()

top_left, top_right = st.columns([1.4, .8], vertical_alignment="top")
with top_left:
    st.info(query["guardrail_message"], icon="🛡️")
    st.markdown("#### What this query does")
    st.write(query["explanation"])
with top_right:
    st.markdown('<div class="pucho-card">', unsafe_allow_html=True)
    st.markdown("<div class='pucho-small'>Model confidence</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='pucho-kpi'>{query['confidence']}%</div>", unsafe_allow_html=True)
    st.caption(f"Estimated result: {query['estimated_rows']} rows")
    st.markdown("</div>", unsafe_allow_html=True)

with st.expander("Inspect generated SQL", expanded=True):
    st.code(query["sql"], language="sql")
    st.caption("This is a UI-only preview. A production API must independently validate this SQL before execution.")

if not query["executed"]:
    st.button(
        "Run approved query",
        type="primary",
        width="content",
        on_click=run_approved_query,
    )
    st.caption("The demo will show mock results. A production service must revalidate the reviewed SQL before it runs.")
    st.stop()

st.markdown('<hr class="pucho-rule">', unsafe_allow_html=True)
result_title, result_badge = st.columns([1.2, .6], vertical_alignment="center")
with result_title:
    st.markdown("### Results")
    st.caption(f"Returned {len(query['rows'])} rows in {query['execution_ms']} ms.")
with result_badge:
    badge("Executed after approval", "success")

st.info(query["result_summary"], icon="📊")
frame = results_frame(query)
chart_x, chart_y = query["chart_columns"]
if not frame.empty and chart_x and chart_y:
    st.bar_chart(frame.set_index(chart_x)[chart_y], width="stretch")
st.dataframe(frame, width="stretch", hide_index=True)

download, feedback, sql_copy = st.columns([.75, 1, .75], vertical_alignment="center")
with download:
    st.download_button(
        "Download CSV",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name=f"{query['id']}.csv",
        mime="text/csv",
        width="stretch",
    )
with feedback:
    st.caption("Was this answer useful?")
    thumb_up, thumb_down = st.columns(2)
    with thumb_up:
        st.button("👍 Yes", key=f"up_{query['id']}", width="stretch", on_click=set_feedback, args=(query["id"], "up"))
    with thumb_down:
        st.button("👎 No", key=f"down_{query['id']}", width="stretch", on_click=set_feedback, args=(query["id"], "down"))
with sql_copy:
    st.download_button(
        "Download SQL",
        data=query["sql"].encode("utf-8"),
        file_name=f"{query['id']}.sql",
        mime="text/plain",
        width="stretch",
    )
