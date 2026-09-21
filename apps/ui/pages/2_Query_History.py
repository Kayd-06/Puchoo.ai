from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.ui.components.app_shell import history_for, initialize_app, page_header, require_workspace


initialize_app("Query History")
page_header(
    "Query history",
    "Every new question is independent",
    "History is an audit trail. A new question is always generated from the current workspace schema and data, never from an earlier answer.",
)
workspace = require_workspace()
if workspace is None:
    st.stop()

history = history_for(workspace["id"])
completed = [item for item in history if item.get("status") == "executed"]
blocked = [item for item in history if item.get("status") == "blocked"]

if not completed:
    with st.container(border=True):
        st.markdown("<span class='status status-warn'>NO COMPLETED CHATS YET</span>", unsafe_allow_html=True)
        st.subheader("Ask your first data question")
        st.write("Completed answers will appear here for review.")
        if st.button("Ask data", type="primary"):
            st.switch_page("pages/1_Ask_a_Question.py")
else:
    for item in completed:
        with st.container(border=True):
            left, right = st.columns((5, 1.35))
            with left:
                st.subheader(str(item.get("question", "Untitled data question")))
                st.caption(
                    f"{str(item.get('created_at', '')).replace('T', ' ')[:19]} · "
                    f"{item.get('row_count', 0)} rows · {item.get('elapsed_ms', 0)} ms"
                )
            with right:
                if st.button("Ask new question", key=f"new_question_{item.get('id', '')}", type="primary", use_container_width=True):
                    st.session_state.chat_context = None
                    st.session_state.active_proposal = None
                    st.session_state.last_execution = None
                    st.session_state.question_input = ""
                    st.switch_page("pages/1_Ask_a_Question.py")
            if item.get("sql"):
                with st.expander("Query details"):
                    st.code(str(item["sql"]), language="sql")

if blocked:
    with st.expander(f"Earlier blocked questions ({len(blocked)})"):
        st.caption("These were stopped before querying your data.")
        for item in blocked:
            st.write(f"• {item.get('question', 'Untitled question')}")
