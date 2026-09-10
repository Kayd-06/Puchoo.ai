from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# ``streamlit run apps/ui/Home.py`` adds ``apps/ui`` to ``sys.path`` rather
# than the repository root. Add the package root explicitly so direct local
# launches, Streamlit Cloud, and tests all resolve the ``apps`` package.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.ui.components.app_shell import active_workspace, history_for, initialize_app, page_header


initialize_app("Overview")
page_header("Workspace analytics", "Answers you can inspect.", "Generate a read-only SQL proposal, approve it deliberately, then compare the result with an independent verifier.")

workspace = active_workspace()
if workspace is None:
    with st.container(border=True):
        st.markdown("<span class='status status-warn'>GET STARTED</span>", unsafe_allow_html=True)
        st.subheader("Connect an existing SQLite database")
        st.write("Pucho only displays analysis from a connected workspace. It never creates, seeds, or modifies source data.")
        if st.button("Connect data", type="primary", key="home_connect_data"):
            st.switch_page("pages/4_My_Data.py")
    st.stop()

history = history_for(workspace["id"])
executed = [entry for entry in history if entry.get("status") == "executed"]
verified = [entry for entry in executed if entry.get("verification", {}).get("status") == "VERIFIED"]
mismatches = [entry for entry in executed if entry.get("verification", {}).get("status") == "VERIFICATION_MISMATCH"]

st.markdown(f"<span class='status status-ok'>ACTIVE WORKSPACE · {workspace['name']}</span>", unsafe_allow_html=True)
st.write("")
cols = st.columns(3)
for column, label, value in zip(cols, ("Executed queries", "Verified answers", "Needs review"), (len(executed), len(verified), len(mismatches))):
    with column:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

st.write("")
left, right = st.columns((1.35, 1))
with left:
    st.subheader("Ask the data")
    st.write("Use a natural-language question. You will always see the generated SQL before anything runs.")
    st.caption("Open Ask a Question from the sidebar to begin.")
with right:
    st.subheader("Recent activity")
    if not history:
        st.caption("No queries have been executed in this workspace yet.")
    else:
        for entry in history[:3]:
            st.write(entry["question"])
            st.caption(f"{entry['status'].replace('_', ' ').title()} · {entry.get('created_at', '')[:16].replace('T', ' ')}")
