"""Shared page shell and session state for the Streamlit MVP."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from html import escape
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from data.demo_data import DEFAULT_GUARDRAILS, SAMPLE_SCHEMA, seeded_history


def configure_page(title: str, icon: str) -> None:
    """Apply the common visual system and initialize the non-sensitive demo state."""
    st.set_page_config(
        page_title=f"{title} · Pucho.ai",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_styles()
    ensure_session_state()
    render_sidebar()


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

          :root {
            --pucho-ink: #171717;
            --pucho-muted: #737373;
            --pucho-primary: #171717;
            --pucho-blue-soft: #f5f5f5;
            --pucho-line: #e5e5e5;
            --pucho-surface: #ffffff;
            --pucho-success: #3f3f46;
            --pucho-warning: #525252;
          }

          /* Clean sans-serif typography */
          html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
          }

          /* Hide Streamlit default menu, footer, and header branding */
          #MainMenu,
          footer,
          [data-testid="stDecoration"],
          [data-testid="stStatusWidget"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
          }
          header[data-testid="stHeader"],
          header[data-testid="stHeader"] [data-testid="stToolbar"] {
            display: flex !important;
            visibility: visible !important;
            height: 0 !important;
            min-height: 0 !important;
            padding: 0 !important;
            background: transparent !important;
            pointer-events: none !important;
          }
          header[data-testid="stHeader"] [data-testid="stExpandSidebarButton"] {
            display: inline-flex !important;
            position: fixed !important;
            top: .75rem !important;
            left: .75rem !important;
            z-index: 1000001 !important;
            pointer-events: auto !important;
          }

          /* Soft, light neutral page background */
          .stApp,
          [data-testid="stAppViewContainer"],
          [data-testid="stAppViewContainer"] > .main {
            background-color: #fafafa !important;
            color: var(--pucho-ink);
          }

          /* Constrain main content to a centered, max-width layout (around 700px) */
          .block-container,
          [data-testid="stAppViewContainer"] > .main .block-container {
            max-width: 700px !important;
            width: 100% !important;
            margin-left: auto !important;
            margin-right: auto !important;
            padding-top: 2rem !important;
            padding-bottom: 3rem !important;
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
          }

          /* Round corners (10-12px) on text inputs */
          div[data-baseweb="input"],
          div[data-baseweb="textarea"],
          div[data-baseweb="base-input"],
          .stTextInput input,
          .stTextArea textarea,
          .stNumberInput input,
          [data-testid="stTextInput"] input,
          [data-testid="stTextArea"] textarea,
          [data-testid="stNumberInput"] input,
          div[data-baseweb="select"] > div {
            border-radius: 11px !important;
          }

          /* Round corners (10-12px) on buttons */
          button,
          .stButton > button,
          .stDownloadButton > button,
          [data-testid="stBaseButton-primary"],
          [data-testid="stBaseButton-secondary"],
          div[data-testid="stFormSubmitButton"] > button {
            border-radius: 11px !important;
            font-weight: 600 !important;
          }

          /* Round corners (10-12px) on alert/success/warning/error boxes */
          [data-testid="stAlert"],
          .stAlert,
          div[data-baseweb="notification"] {
            border-radius: 11px !important;
          }

          /* Round corners (10-12px) on expander sections */
          [data-testid="stExpander"],
          [data-testid="stExpander"] details,
          details {
            border-radius: 11px !important;
            overflow: hidden !important;
          }

          /* Round corners (10-12px) on code blocks */
          [data-testid="stCode"],
          [data-testid="stCodeBlock"],
          div[data-testid="stCodeBlock"] pre,
          .stCode,
          pre,
          pre code {
            border-radius: 11px !important;
            overflow: hidden !important;
          }

          /* Primary button accent color */
          button[kind="primary"],
          .stButton > button[kind="primary"],
          [data-testid="stBaseButton-primary"],
          div[data-testid="stFormSubmitButton"] > button {
            background-color: #171717 !important;
            border-color: #171717 !important;
            color: #ffffff !important;
          }

          /* Input focus state accent color */
          div[data-baseweb="input"]:focus-within,
          div[data-baseweb="textarea"]:focus-within,
          div[data-baseweb="base-input"]:focus-within,
          div[data-baseweb="select"]:focus-within > div,
          .stTextInput input:focus,
          .stTextArea textarea:focus,
          .stNumberInput input:focus {
            border-color: #171717 !important;
            box-shadow: 0 0 0 1.5px #171717 !important;
            outline: none !important;
          }

          /* Subtle hover states on buttons */
          button[kind="primary"]:hover,
          .stButton > button[kind="primary"]:hover,
          [data-testid="stBaseButton-primary"]:hover,
          div[data-testid="stFormSubmitButton"] > button:hover {
            background-color: #000000 !important;
            border-color: #000000 !important;
            color: #ffffff !important;
            transition: background-color 0.15s ease, border-color 0.15s ease;
          }

          button[kind="secondary"]:hover,
          .stButton > button:not([kind="primary"]):hover,
          .stDownloadButton > button:hover,
          [data-testid="stBaseButton-secondary"]:hover {
            background-color: #f5f5f5 !important;
            border-color: #a3a3a3 !important;
            color: #171717 !important;
            transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
          }

          /* Shared workspace rail */
          [data-testid="stSidebar"] {
            min-width: 236px !important;
            max-width: 236px !important;
            background: #ffffff !important;
            border-right: 1px solid var(--pucho-line);
          }
          [data-testid="stSidebarContent"] { padding: 1.55rem .9rem !important; }
          [data-testid="stSidebarHeader"] {
            display: block !important;
            position: relative !important;
            width: 100% !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
          }
          [data-testid="stSidebarHeader"] [data-testid="stLogoSpacer"],
          [data-testid="stSidebarHeader"] [data-testid="stSidebarLogo"],
          [data-testid="stSidebarNav"] { display: none !important; }
          [data-testid="stSidebarUserContent"] { padding-top: 0 !important; }
          [data-testid="stSidebarCollapseButton"] {
            display: block !important;
            visibility: visible !important;
            position: absolute !important;
            top: .35rem !important;
            right: .15rem !important;
            z-index: 2 !important;
            margin: 0 !important;
          }
          [data-testid="stSidebarCollapseButton"] > button,
          button[data-testid="stExpandSidebarButton"] {
            width: 2rem !important;
            min-width: 2rem !important;
            height: 2rem !important;
            min-height: 2rem !important;
            padding: 0 !important;
            border: 1px solid #d4d4d4 !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            color: #171717 !important;
            box-shadow: none !important;
          }
          [data-testid="stSidebarCollapseButton"] > button:hover,
          button[data-testid="stExpandSidebarButton"]:hover {
            border-color: #a3a3a3 !important;
            background: #f5f5f5 !important;
          }
          .sidebar-brand {
            display: flex;
            align-items: center;
            gap: .68rem;
            margin: 0 .42rem 1.8rem;
          }
          .sidebar-mark {
            position: relative;
            width: 30px;
            height: 30px;
            flex: 0 0 auto;
            display: grid;
            place-items: center;
            border-radius: 8px;
            color: #ffffff;
            background: var(--pucho-primary);
          }
          .sidebar-mark::before {
            content: "";
            width: 13px;
            height: 9px;
            border: 1.6px solid currentColor;
            border-radius: 3px;
          }
          .sidebar-mark::after {
            content: "";
            position: absolute;
            left: 9px;
            top: 18px;
            width: 4px;
            height: 4px;
            border-bottom: 1.6px solid currentColor;
            border-left: 1.6px solid currentColor;
            transform: rotate(-45deg);
          }
          .sidebar-product, .sidebar-caption { display: block; }
          .sidebar-product { color: var(--pucho-ink); font-size: 1rem; font-weight: 750; letter-spacing: -.035em; }
          .sidebar-caption { margin-top: .08rem; color: #a3a3a3; font-size: .64rem; font-weight: 700; letter-spacing: .065em; text-transform: uppercase; }
          .sidebar-label { margin: 0 .58rem .42rem; color: #a3a3a3; font-size: .67rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
          [data-testid="stSidebar"] [data-testid="stPageLink"] { margin: .12rem 0; }
          [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
            min-height: 40px;
            border-radius: 8px;
            color: #525252;
            font-size: .87rem;
            font-weight: 600;
            transition: background-color .16s ease, color .16s ease;
          }
          [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] { color: #a3a3a3; }
          [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {
            color: #171717;
            background: #f5f5f5;
          }
          [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:focus-visible {
            outline: 3px solid rgba(23, 23, 23, .18);
            outline-offset: 2px;
          }
          .sidebar-divider { height: 1px; margin: 1.45rem .42rem 1rem; background: var(--pucho-line); }
          .sidebar-status { display: grid; grid-template-columns: 7px 1fr; column-gap: .48rem; align-items: center; margin: 0 .42rem; color: #737373; font-size: .76rem; }
          .sidebar-status i { width: 7px; height: 7px; grid-row: span 2; border-radius: 50%; background: #525252; }
          .sidebar-status span { color: #525252; font-weight: 650; }
          .sidebar-status small { margin-top: .1rem; color: #a3a3a3; font-size: .69rem; }

          /* Shell specific components */
          h1, h2, h3 { color: var(--pucho-ink) !important; letter-spacing: -0.025em; }
          h1 { font-weight: 720 !important; }
          .pucho-brand { font-size: 1.25rem; font-weight: 760; letter-spacing: -.04em; color: var(--pucho-ink); margin-bottom: .2rem; }
          .pucho-brand span { color: var(--pucho-primary); }
          .pucho-eyebrow { color: var(--pucho-primary); font-size: .77rem; font-weight: 750; letter-spacing: .075em; text-transform: uppercase; }
          .pucho-muted { color: var(--pucho-muted); }
          .pucho-card { background: var(--pucho-surface); border: 1px solid var(--pucho-line); border-radius: 11px; padding: 1.1rem 1.2rem; box-shadow: 0 1px 2px rgba(0, 0, 0, .02); }
          .pucho-card h3 { margin: 0 0 .3rem 0; font-size: 1rem; }
          .pucho-kpi { font-size: 1.65rem; line-height: 1; font-weight: 750; color: var(--pucho-ink); margin-bottom: .35rem; }
          .pucho-badge { display: inline-flex; align-items: center; gap: .35rem; border-radius: 999px; padding: .25rem .58rem; font-size: .76rem; font-weight: 700; line-height: 1; }
          .pucho-badge.success { background: #f5f5f5; color: var(--pucho-success); }
          .pucho-badge.info { background: var(--pucho-blue-soft); color: #262626; }
          .pucho-badge.warning { background: #f5f5f5; color: var(--pucho-warning); }
          .pucho-badge.neutral { background: #f5f5f5; color: #525252; }
          .pucho-rule { border: 0; border-top: 1px solid var(--pucho-line); margin: 1.45rem 0; }
          .pucho-hero { max-width: 700px; padding: 1.6rem 0 1.5rem; }
          .pucho-hero h1 { font-size: clamp(2.15rem, 5vw, 3.6rem); line-height: 1.05; margin: .3rem 0 .85rem; }
          .pucho-hero p { font-size: 1.12rem; line-height: 1.65; color: var(--pucho-muted); }
          .pucho-step { font-size: .76rem; font-weight: 750; color: var(--pucho-primary); letter-spacing: .04em; text-transform: uppercase; }
          .pucho-sidebar-card { border: 1px solid var(--pucho-line); border-radius: 11px; padding: .78rem .82rem; background: #ffffff; margin: .75rem 0 1.1rem; }
          .pucho-small { font-size: .78rem; color: var(--pucho-muted); line-height: 1.5; }
          [data-testid="stMetric"] { background: var(--pucho-surface); border: 1px solid var(--pucho-line); border-radius: 11px; padding: .85rem 1rem; }
          [data-testid="stMetricLabel"] { color: var(--pucho-muted); }
          @media (max-width: 700px) { .block-container { padding: 1.15rem .9rem 2rem; } .pucho-hero h1 { font-size: 2.25rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def ensure_session_state() -> None:
    defaults: dict[str, Any] = {
        "connection_name": "Northstar demo database",
        "connection_status": "Demo mode · no database",
        "schema_refreshed_at": "Just now",
        "schema": SAMPLE_SCHEMA,
        "guardrail_settings": deepcopy(DEFAULT_GUARDRAILS),
        "query_history": seeded_history(),
        "draft_question": "",
        "generated_query": None,
        "selected_history_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_sidebar() -> None:
    """Render the same workspace navigation used on the Home page."""
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
              <span class="sidebar-mark" aria-hidden="true"></span>
              <span>
                <span class="sidebar-product">pucho.ai</span>
                <span class="sidebar-caption">Analytics workspace</span>
              </span>
            </div>
            <div class="sidebar-label">Workspace</div>
            """,
            unsafe_allow_html=True,
        )
        _workspace_page_link(
            "Home.py",
            label="Ask data",
            icon=":material/chat_bubble_outline:",
        )
        _workspace_page_link(
            "pages/4_My_Data.py",
            label="My data",
            icon=":material/database:",
        )
        _workspace_page_link(
            "pages/2_Query_History.py",
            label="Query history",
            icon=":material/history:",
        )
        _workspace_page_link(
            "pages/3_Guardrail_Settings.py",
            label="Guardrails",
            icon=":material/admin_panel_settings:",
        )
        st.markdown(
            """
            <div class="sidebar-divider"></div>
            <div class="sidebar-status">
              <i aria-hidden="true"></i>
              <span>Demo workspace</span>
              <small>No source connected</small>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _workspace_page_link(page: str, *, label: str, icon: str) -> None:
    """Render native navigation, with a static fallback for isolated page tests."""
    try:
        st.page_link(page, label=label, icon=icon, width="stretch")
    except StreamlitPageNotFoundError:
        st.markdown(
            f'<div class="sidebar-link-fallback">{escape(label)}</div>',
            unsafe_allow_html=True,
        )


def badge(text: str, tone: str = "neutral") -> None:
    allowed_tones = {"success", "info", "warning", "neutral"}
    safe_tone = tone if tone in allowed_tones else "neutral"
    st.markdown(
        f'<span class="pucho-badge {safe_tone}">{escape(text)}</span>',
        unsafe_allow_html=True,
    )


def section_heading(eyebrow: str, title: str, description: str | None = None) -> None:
    st.markdown(f'<div class="pucho-eyebrow">{escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.markdown(f"## {escape(title)}")
    if description:
        st.markdown(f'<div class="pucho-muted">{escape(description)}</div>', unsafe_allow_html=True)


def format_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b · %I:%M %p")
    except ValueError:
        return value


def upsert_history(query: dict[str, Any]) -> None:
    """Add a generated proposal or update that same proposal after execution."""
    history = st.session_state.query_history
    for index, item in enumerate(history):
        if item["id"] == query["id"]:
            history[index] = deepcopy(query)
            return
    history.insert(0, deepcopy(query))


def set_feedback(query_id: str, value: str) -> None:
    for item in st.session_state.query_history:
        if item["id"] == query_id:
            item["feedback"] = value
    current = st.session_state.generated_query
    if current and current["id"] == query_id:
        current["feedback"] = value


def clear_query_draft() -> None:
    st.session_state.draft_question = ""
    st.session_state.generated_query = None
