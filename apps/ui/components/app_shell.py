"""Shared Streamlit shell and session-scoped workspace state."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

import streamlit as st

from apps.core.local_state import load_local_state, save_local_state


DEFAULT_GUARDRAILS: dict[str, Any] = {"max_rows": 500, "timeout_seconds": 30, "confirm_complex_queries": True}


def initialize_app(page_title: str) -> None:
    st.set_page_config(page_title=f"Puchoo · {page_title}", page_icon="✦", layout="wide", initial_sidebar_state="expanded")
    persisted = load_local_state() if not st.session_state.get("local_state_loaded") else {}
    defaults: dict[str, Any] = {
        "workspaces": persisted.get("workspaces", {}),
        "active_workspace_id": persisted.get("active_workspace_id"),
        "workspace_guardrails": persisted.get("workspace_guardrails", {}),
        "query_history": persisted.get("query_history", {}),
        "active_proposal": None,
        "profile": {"name": "", "email": "", "department": "", "timezone": "Asia/Kolkata", **persisted.get("profile", {})},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state.local_state_loaded = True
    st.markdown(
        """<style>
        .stApp { background:#f8f8ff; color:#101b39; }
        [data-testid="stHeader"] { background:rgba(250,251,255,.92); }
        [data-testid="stSidebar"] { background:#ffffff; border-right:1px solid #e6e9f5; }
        [data-testid="stSidebar"] [data-testid="stSidebarHeader"] { height:0 !important; min-height:0 !important; padding:0 !important; }
        [data-testid="stSidebar"] [data-testid="stSidebarHeader"] button { position:absolute; top:.45rem; right:.45rem; z-index:4; }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding-top:.7rem !important; }
        [data-testid="stSidebar"] > div:first-child { padding-top:0 !important; }
        [data-testid="stSidebarNav"] { display:none; }
        [data-testid="stSidebarNav"] a { border-radius:9px; margin:.08rem .45rem; color:#34405f; font-weight:600; }
        [data-testid="stSidebarNav"] a[aria-current="page"] { background:#0a58f5; color:white; }
        .block-container { max-width:1220px; padding-top:1.25rem; padding-bottom:3.5rem; }
        .puchoo-mark { color:#101b39; font-size:1.18rem; font-weight:800; letter-spacing:-.05em; }
        .puchoo-mark span { color:#0b63f6; }.puchoo-tag { color:#087f58; background:#d8fae9; border-radius:999px; padding:.17rem .48rem; font-size:.65rem; font-weight:800; margin-left:.55rem; vertical-align:middle; letter-spacing:.03em; }
        .eyebrow { color:#1365eb; font-weight:750; font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; }
        .hero-title { color:#101b39; font-size:2.45rem; font-weight:800; line-height:1.1; letter-spacing:-.06em; margin:.25rem 0 .45rem; }
        .muted { color:#59637b; max-width:690px; line-height:1.55; }
        .metric-card, .surface-card { background:#fff; border:1px solid #e7ebf7; box-shadow:0 7px 18px rgba(28,46,92,.045); border-radius:15px; padding:1.05rem 1.15rem; }
        .metric-card { min-height:94px; }.metric-label { color:#65708b; font-size:.77rem; font-weight:700; }.metric-value { color:#142143; font-size:1.65rem; font-weight:800; margin-top:.23rem; }.workspace-value { color:#142143; font-size:1.08rem; font-weight:800; line-height:1.3; margin-top:.35rem; overflow-wrap:anywhere; }
        .status { display:inline-block; padding:.24rem .58rem; border-radius:999px; font-size:.69rem; letter-spacing:.015em; font-weight:800; }.status-ok { background:#d9faeb; color:#087d58; }.status-warn { background:#fff1d6; color:#9b5d00; }.status-bad { background:#ffeaee; color:#c62442; }
        .workspace-chip { background:#fff; border:1px solid #e7ebf7; box-shadow:0 4px 12px rgba(28,46,92,.04); border-radius:11px; padding:.62rem .78rem; color:#33405d; font-size:.8rem; font-weight:650; }
        .small-label { color:#68728b; font-weight:800; font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; }
        .stButton > button, .stDownloadButton > button { border-radius:9px; font-weight:700; min-height:2.45rem; border-color:#dfe5f5; }
        .stButton > button[kind="primary"] { background:#2563eb; border-color:#2563eb; color:#fff; box-shadow:0 5px 10px rgba(37,99,235,.18); }
        .stButton > button[kind="primary"]:disabled { background:#b9cbfb; border-color:#b9cbfb; color:#fff; box-shadow:none; }
        [data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input { border-radius:12px; border-color:#e1e6f3; background:#fff; }
        [data-testid="stTextArea"] textarea:focus, [data-testid="stTextInput"] input:focus { border-color:#0a58f5; box-shadow:0 0 0 3px rgba(10,88,245,.09); }
        [data-testid="stDataFrame"] { border:1px solid #e7ebf7; border-radius:12px; overflow:hidden; }
        .sidebar-note { background:#eff8f4; color:#087d58; border-radius:10px; padding:.65rem .7rem; font-size:.75rem; line-height:1.35; }
        @media (max-width: 900px) {
          .block-container { padding:1rem 1rem 2.5rem; }
          .hero-title { font-size:2rem; letter-spacing:-.045em; }
          .workspace-chip[style] { float:none !important; margin:1rem 0 0 !important; max-width:none !important; }
          .metric-card { min-height:auto; }
        }
        </style>""",
        unsafe_allow_html=True,
    )
    render_sidebar(page_title)


def active_workspace() -> dict[str, Any] | None:
    workspace_id = st.session_state.active_workspace_id
    return st.session_state.workspaces.get(workspace_id) if workspace_id else None


def workspace_guardrails(workspace_id: str) -> dict[str, Any]:
    configured = st.session_state.workspace_guardrails.get(workspace_id, {})
    return {**DEFAULT_GUARDRAILS, **configured}


def history_for(workspace_id: str) -> list[dict[str, Any]]:
    return st.session_state.query_history.get(workspace_id, [])


def add_history(workspace_id: str, item: dict[str, Any]) -> None:
    st.session_state.query_history.setdefault(workspace_id, []).insert(0, item)
    persist_app_state()


def persist_app_state() -> None:
    """Save local workspace state after a user-initiated change.

    Local imports and audit records survive browser refresh. Server workspaces
    are intentionally omitted because their credentials must never be stored.
    """

    save_local_state(
        workspaces=st.session_state.workspaces,
        active_workspace_id=st.session_state.active_workspace_id,
        workspace_guardrails=st.session_state.workspace_guardrails,
        query_history=st.session_state.query_history,
        profile=st.session_state.profile,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def render_sidebar(page_title: str) -> None:
    with st.sidebar:
        st.markdown('<div class="puchoo-mark">◈ <span>Pucho</span> AI <span class="puchoo-tag">READ ONLY</span></div>', unsafe_allow_html=True)
        st.caption("Safe Data Assistant")
        st.divider()
        spaces = st.session_state.workspaces
        destinations = (
            ("Ask Data", "pages/1_Ask_a_Question.py"),
            ("Connect Data", "pages/4_My_Data.py"),
            ("History", "pages/2_Query_History.py"),
            ("Settings", "pages/3_Guardrail_Settings.py"),
        )
        active_label = {
            "Ask a Question": "Ask Data",
            "My Data": "Connect Data",
            "Query History": "History",
            "Guardrails": "Settings",
        }.get(page_title)
        for label, destination in destinations:
            if st.button(label, key=f"nav_{label}", type="primary" if label == active_label else "secondary", use_container_width=True):
                st.switch_page(destination)
        st.divider()
        if spaces:
            ids = list(spaces)
            current = st.session_state.active_workspace_id
            initial = ids.index(current) if current in ids else 0
            selected = st.selectbox("Workspace", ids, index=initial, format_func=lambda key: spaces[key]["name"], key="workspace_picker")
            if selected != current:
                st.session_state.active_workspace_id = selected
                st.session_state.active_proposal = None
                persist_app_state()
                st.rerun()
            workspace = spaces[selected]
            st.markdown(f'<div class="workspace-chip"><div class="small-label">Active workspace</div>{escape(workspace["name"])}</div>', unsafe_allow_html=True)
        else:
            st.caption("No workspace connected")
        st.write("")
        st.markdown('<div class="sidebar-note">● Read-only mode<br>Every query is validated before it can run.</div>', unsafe_allow_html=True)


def page_header(eyebrow: str, title: str, subtitle: str) -> None:
    workspace = active_workspace()
    target = escape(workspace["name"]) if workspace else "No data source connected"
    st.markdown(
        f'<div class="eyebrow">{escape(eyebrow)}</div><div class="hero-title">{escape(title)}</div>'
        f'<div class="muted">{escape(subtitle)}</div><div class="workspace-chip" style="float:right;margin-top:-4.9rem;max-width:250px;"><div class="small-label">Target workspace</div>{target}</div>',
        unsafe_allow_html=True,
    )
    st.write("")


def require_workspace() -> dict[str, Any] | None:
    workspace = active_workspace()
    if workspace is None:
        with st.container(border=True):
            st.markdown("<span class='status status-warn'>WORKSPACE REQUIRED</span>", unsafe_allow_html=True)
            st.subheader("Connect a data source to continue")
            st.write("Pucho does not create sample records or fabricate analysis. Upload an existing SQLite file or connect one by local path, then this workspace will show its real schema, query activity, and results.")
            if st.button("Connect data", type="primary", key="onboarding_connect_data"):
                st.switch_page("pages/4_My_Data.py")
    return workspace
