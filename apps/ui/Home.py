"""A focused, data-source-neutral workspace for Ask Your Data."""

from html import escape
from pathlib import Path
import sys
from textwrap import dedent

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from components.app_shell import render_sidebar


st.set_page_config(
    page_title="Ask Your Data · Pucho.ai",
    page_icon=":material/query_stats:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def clear_question() -> None:
    """Reset the landing composer without retaining a submitted question."""
    st.session_state.pop("submitted_question", None)
    st.session_state["landing_question"] = ""


render_sidebar()


st.html(
    dedent(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

          :root {
            --canvas: #fafafa;
            --surface: #ffffff;
            --ink: #171717;
            --muted: #737373;
            --line: #e5e5e5;
            --primary: #171717;
            --primary-soft: #f5f5f5;
          }

          html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
          }
          #MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {
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
          .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main {
            min-height: 100vh;
            background: var(--canvas) !important;
            color: var(--ink);
          }
          [data-testid="stAppViewContainer"] > .main .block-container,
          .block-container {
            max-width: 1120px !important;
            padding: 2.5rem 3.5rem 4rem !important;
          }

          /* Workspace rail */
          [data-testid="stSidebar"] {
            min-width: 236px !important;
            max-width: 236px !important;
            background: #ffffff !important;
            border-right: 1px solid var(--line);
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
          [data-testid="stSidebarNav"] {
            display: none !important;
          }
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
            background: var(--primary);
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
          .sidebar-product { color: var(--ink); font-size: 1rem; font-weight: 750; letter-spacing: -.035em; }
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
            background: var(--primary-soft);
          }
          [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:focus-visible {
            outline: 3px solid rgba(23, 23, 23, .18);
            outline-offset: 2px;
          }
          .sidebar-divider { height: 1px; margin: 1.45rem .42rem 1rem; background: var(--line); }
          .sidebar-status { display: grid; grid-template-columns: 7px 1fr; column-gap: .48rem; align-items: center; margin: 0 .42rem; color: #737373; font-size: .76rem; }
          .sidebar-status i { width: 7px; height: 7px; grid-row: span 2; border-radius: 50%; background: #525252; }
          .sidebar-status span { color: #525252; font-weight: 650; }
          .sidebar-status small { margin-top: .1rem; color: #a3a3a3; font-size: .69rem; }

          /* Focused page workspace */
          .workspace-header {
            max-width: 820px;
            margin: 0 auto 2rem;
          }
          .workspace-kicker { margin: 0 0 .45rem; color: var(--primary); font-size: .7rem; font-weight: 750; letter-spacing: .075em; text-transform: uppercase; }
          .workspace-header h1 { margin: 0; color: var(--ink); font-size: clamp(2rem, 4vw, 2.6rem); font-weight: 750; letter-spacing: -.05em; line-height: 1.08; }
          .workspace-header p { margin: .65rem 0 0; color: var(--muted); font-size: 1rem; line-height: 1.55; }
          .workspace-status { display: inline-flex; align-items: center; gap: .45rem; margin-top: .9rem; color: #737373; font-size: .8rem; font-weight: 600; }
          .workspace-status::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: #525252; }

          [data-testid="stForm"] {
            max-width: 820px !important;
            margin: 0 auto !important;
            padding: 1.45rem !important;
            border: 1px solid var(--line) !important;
            border-radius: 12px !important;
            background: var(--surface) !important;
            box-shadow: none !important;
          }
          .composer-heading { margin-bottom: 1.1rem; }
          .composer-heading h2 { margin: 0; color: var(--ink); font-size: 1.12rem; font-weight: 700; letter-spacing: -.025em; }
          .composer-heading p { margin: .35rem 0 0; color: var(--muted); font-size: .88rem; line-height: 1.5; }
          [data-testid="stForm"] [data-testid="stHorizontalBlock"] { align-items: end; gap: .7rem; }
          div[data-testid="stTextInput"] { margin-bottom: 0 !important; }
          [data-testid="stTextInputRootElement"] {
            min-height: 54px !important;
            height: 54px !important;
            border: 1px solid #d4d4d4 !important;
            border-radius: 9px !important;
            background: #ffffff !important;
            box-shadow: none !important;
          }
          div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
          div[data-testid="stTextInput"] [data-testid="stTextInputRootElement"]:focus-within {
            border-color: var(--primary) !important;
            box-shadow: 0 0 0 3px rgba(23, 23, 23, .12) !important;
          }
          div[data-testid="stTextInput"] input { color: var(--ink) !important; font-size: .96rem !important; }
          div[data-testid="stTextInput"] input::placeholder { color: #a3a3a3; }
          [data-testid="stTextInputIcon"] { color: #737373 !important; }
          div[data-testid="stFormSubmitButton"] { margin: 0 !important; }
          div[data-testid="stFormSubmitButton"] > button {
            min-height: 54px !important;
            border: 0 !important;
            border-radius: 9px !important;
            background: var(--primary) !important;
            box-shadow: none !important;
            font-weight: 700 !important;
          }
          div[data-testid="stFormSubmitButton"] > button:hover { background: #000000 !important; }

          .workspace-note {
            max-width: 820px;
            margin: 1rem auto 0;
            padding-left: .8rem;
            border-left: 2px solid #d4d4d4;
            color: #737373;
            font-size: .84rem;
            line-height: 1.5;
          }
          .workspace-note strong { color: #262626; }
          .submitted-question { margin-top: .65rem; color: #262626; }
          .submitted-question span { display: block; margin-bottom: .18rem; color: #a3a3a3; font-size: .65rem; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; }
          .stButton { max-width: 820px; margin: .8rem auto 0; }
          .stButton > button { border: 1px solid #d4d4d4 !important; border-radius: 8px !important; color: #525252 !important; background: #ffffff !important; font-weight: 650 !important; }
          .workspace-footer { max-width: 820px; margin: 3.4rem auto 0; padding-top: 1rem; border-top: 1px solid var(--line); color: #a3a3a3; font-size: .76rem; }
          .workspace-footer span + span::before { content: "·"; margin: 0 .5rem; color: #d4d4d4; }

          @media (max-width: 900px) {
            [data-testid="stAppViewContainer"] > .main .block-container, .block-container { padding: 1.5rem 1.25rem 3rem !important; }
          }
          @media (max-width: 640px) {
            .workspace-header { margin-bottom: 1.5rem; }
            .workspace-header h1 { font-size: 2rem; }
            [data-testid="stForm"] { padding: 1.1rem !important; }
            [data-testid="stForm"] [data-testid="stHorizontalBlock"] { gap: .5rem; }
            [data-testid="stTextInputRootElement"], div[data-testid="stFormSubmitButton"] > button { min-height: 50px !important; height: 50px !important; }
          }
        </style>

        <header class="workspace-header">
          <div class="workspace-kicker">Analytics workspace</div>
          <h1>Ask your data</h1>
          <p>Get a transparent, reviewable query from a plain-language question.</p>
          <div class="workspace-status">Demo workspace · No source connected</div>
        </header>
        """
    )
)


with st.form("ask_data_form", border=False, enter_to_submit=False):
    st.html(
        """
        <div class="composer-heading" id="ask">
          <h2>What would you like to know?</h2>
          <p>Ask naturally. You will review the proposed query before anything runs.</p>
        </div>
        """
    )
    question_column, submit_column = st.columns((1, 0.2), gap="small", vertical_alignment="bottom")
    with question_column:
        question = st.text_input(
            "Your question",
            key="landing_question",
            placeholder="Ask a question about your data…",
            label_visibility="collapsed",
            icon=":material/search:",
        )
    with submit_column:
        submitted = st.form_submit_button(
            "Ask",
            type="primary",
            icon=":material/arrow_forward:",
            use_container_width=True,
        )

if submitted:
    cleaned_question = question.strip()
    if cleaned_question:
        st.session_state["submitted_question"] = cleaned_question
    else:
        st.error("Write a question before continuing.")

submitted_question = st.session_state.get("submitted_question")
if submitted_question:
    st.html(
        dedent(
            f"""
            <div class="workspace-note" aria-live="polite">
              <strong>Question ready</strong>
              <p class="submitted-question"><span>Your question</span>{escape(submitted_question)}</p>
              Live answers will appear only after a connected data service returns them.
            </div>
            """
        )
    )
    st.button("Clear question", on_click=clear_question)
else:
    st.html(
        """
        <div class="workspace-note" aria-live="polite">
          <strong>Read-only by default.</strong> This workspace never invents a result, table, or source query.
        </div>
        """
    )

st.html(
    """
    <footer class="workspace-footer">
      <span>Query review required</span><span>Session activity is kept locally</span>
    </footer>
    """
)
