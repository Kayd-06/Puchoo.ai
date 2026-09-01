"""Shared page shell and session state for the Streamlit MVP."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from html import escape
from typing import Any

import streamlit as st

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
          :root {
            --pucho-ink: #15222d;
            --pucho-muted: #64748b;
            --pucho-primary: #155eef;
            --pucho-blue-soft: #eef4ff;
            --pucho-line: #e5eaf1;
            --pucho-surface: #ffffff;
            --pucho-success: #067647;
            --pucho-warning: #b54708;
          }
          .stApp { background: #f8fafc; color: var(--pucho-ink); }
          [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--pucho-line); }
          [data-testid="stSidebar"] > div:first-child { padding-top: 1.1rem; }
          [data-testid="stSidebarNav"] { padding-top: .7rem; }
          [data-testid="stSidebarNav"] a { border-radius: 9px; padding: .36rem .55rem; }
          .block-container { max-width: 1240px; padding-top: 2.35rem; padding-bottom: 3rem; }
          h1, h2, h3 { color: var(--pucho-ink) !important; letter-spacing: -0.025em; }
          h1 { font-weight: 720 !important; }
          .pucho-brand { font-size: 1.25rem; font-weight: 760; letter-spacing: -.04em; color: var(--pucho-ink); margin-bottom: .2rem; }
          .pucho-brand span { color: var(--pucho-primary); }
          .pucho-eyebrow { color: var(--pucho-primary); font-size: .77rem; font-weight: 750; letter-spacing: .075em; text-transform: uppercase; }
          .pucho-muted { color: var(--pucho-muted); }
          .pucho-card { background: var(--pucho-surface); border: 1px solid var(--pucho-line); border-radius: 14px; padding: 1.1rem 1.2rem; box-shadow: 0 1px 2px rgba(15, 23, 42, .02); }
          .pucho-card h3 { margin: 0 0 .3rem 0; font-size: 1rem; }
          .pucho-kpi { font-size: 1.65rem; line-height: 1; font-weight: 750; color: var(--pucho-ink); margin-bottom: .35rem; }
          .pucho-badge { display: inline-flex; align-items: center; gap: .35rem; border-radius: 999px; padding: .25rem .58rem; font-size: .76rem; font-weight: 700; line-height: 1; }
          .pucho-badge.success { background: #ecfdf3; color: var(--pucho-success); }
          .pucho-badge.info { background: var(--pucho-blue-soft); color: #1849a9; }
          .pucho-badge.warning { background: #fffaeb; color: var(--pucho-warning); }
          .pucho-badge.neutral { background: #f1f5f9; color: #475569; }
          .pucho-rule { border: 0; border-top: 1px solid var(--pucho-line); margin: 1.45rem 0; }
          .pucho-hero { max-width: 760px; padding: 1.6rem 0 1.5rem; }
          .pucho-hero h1 { font-size: clamp(2.15rem, 5vw, 3.6rem); line-height: 1.05; margin: .3rem 0 .85rem; }
          .pucho-hero p { font-size: 1.12rem; line-height: 1.65; color: var(--pucho-muted); }
          .pucho-step { font-size: .76rem; font-weight: 750; color: var(--pucho-primary); letter-spacing: .04em; text-transform: uppercase; }
          .pucho-sidebar-card { border: 1px solid var(--pucho-line); border-radius: 11px; padding: .78rem .82rem; background: #fbfdff; margin: .75rem 0 1.1rem; }
          .pucho-small { font-size: .78rem; color: var(--pucho-muted); line-height: 1.5; }
          .stButton > button, .stDownloadButton > button { border-radius: 9px; font-weight: 650; }
          .stButton > button[kind="primary"] { background: var(--pucho-primary); border-color: var(--pucho-primary); }
          .stTextArea textarea { border-radius: 10px; }
          [data-testid="stMetric"] { background: var(--pucho-surface); border: 1px solid var(--pucho-line); border-radius: 12px; padding: .85rem 1rem; }
          [data-testid="stMetricLabel"] { color: var(--pucho-muted); }
          .stAlert { border-radius: 10px; }
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
    with st.sidebar:
        st.markdown('<div class="pucho-brand">pucho<span>.ai</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="pucho-small">Natural-language analytics, with a human review step.</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="pucho-sidebar-card">
              <div class="pucho-small">Connection</div>
              <div style="font-weight:700; margin:.12rem 0 .35rem;">{escape(st.session_state.connection_name)}</div>
              <span class="pucho-badge info">● {escape(st.session_state.connection_status)}</span>
              <div class="pucho-small" style="margin-top:.55rem;">Schema refreshed {escape(st.session_state.schema_refreshed_at)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("Safety promise", expanded=False):
            st.caption(
                "This UI demo never connects to a database. In production, the API must validate SQL server-side and wait for explicit approval before execution."
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
