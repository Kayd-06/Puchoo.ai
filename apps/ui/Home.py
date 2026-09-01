"""Working, data-source-neutral first screen for Ask Your Data."""

from html import escape
from textwrap import dedent

import streamlit as st


st.set_page_config(
    page_title="Ask Your Data",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def clear_question() -> None:
    """Reset the local UI state without retaining a submitted question."""
    st.session_state.pop("submitted_question", None)
    st.session_state["landing_question"] = ""


st.html(
    dedent(
        """
        <style>
          :root {
            --canvas: #f8f9ff;
            --ink: #101a31;
            --muted: #697386;
            --line: #c8c9df;
            --primary: #3127dc;
            --soft-blue: #edf3ff;
            --panel: #ffffff;
          }

          .stApp, [data-testid="stAppViewContainer"] { background: var(--canvas); }
          header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
          [data-testid="collapsedControl"], [data-testid="stSidebar"], #MainMenu, footer { display: none !important; }
          [data-testid="stAppViewContainer"] > .main { background: var(--canvas); }
          [data-testid="stAppViewContainer"] > .main .block-container {
            max-width: none;
            padding: 0 46px 72px;
          }

          .ask-screen, .ask-screen * { box-sizing: border-box; }
          .ask-screen {
            color: var(--ink);
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          }
          .top-nav {
            height: 74px;
            width: 100%;
            border: 1px solid #eff0f7;
            border-top: 0;
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            align-items: center;
            padding: 0 29px;
            background: rgba(250, 251, 255, .68);
          }
          .brand {
            color: var(--primary);
            font-size: 24px;
            font-weight: 760;
            letter-spacing: -.035em;
          }
          .nav-links { display: flex; align-self: stretch; align-items: center; gap: 28px; }
          .nav-link {
            align-self: stretch;
            display: inline-flex;
            align-items: center;
            position: relative;
            color: #15172a;
            font-size: 18px;
            text-decoration: none;
          }
          .nav-link.active { color: var(--primary); }
          .nav-link.active::after {
            content: "";
            position: absolute;
            right: 0;
            bottom: 18px;
            left: 0;
            height: 2px;
            border-radius: 99px;
            background: var(--primary);
          }
          .profile { justify-self: end; width: 26px; height: 26px; color: var(--primary); }
          .ask-hero {
            max-width: 895px;
            margin: 0 auto;
            padding-top: 76px;
            text-align: center;
          }
          .chat-mark {
            width: 76px;
            height: 76px;
            display: grid;
            place-items: center;
            margin: 0 auto;
            border-radius: 50%;
            color: var(--primary);
            background: #e0ebff;
          }
          .ask-hero h1 {
            margin: 24px 0 12px;
            color: var(--ink);
            font-size: 40px;
            line-height: 1.12;
            font-weight: 750;
            letter-spacing: -.044em;
          }
          .ask-hero p {
            margin: 0;
            color: var(--muted);
            font-size: 17px;
            line-height: 1.5;
          }

          [data-testid="stForm"] {
            width: 100% !important;
            max-width: 895px !important;
            margin: 76px auto 0 !important;
            padding: 24px 24px 18px !important;
            border: 0 !important;
            border-radius: 14px;
            background: var(--panel) !important;
            box-shadow: 0 9px 24px rgba(52, 58, 113, .055);
            box-sizing: border-box;
          }
          [data-testid="stTextAreaRootElement"],
          [data-testid="stTextAreaRootElement"]:focus-within {
            border: 0 !important;
            border-color: transparent !important;
            border-radius: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            outline: 0 !important;
          }
          div[data-testid="stTextArea"] textarea {
            min-height: 53px !important;
            max-height: 120px !important;
            padding: 8px 0 6px 40px !important;
            border: 0 !important;
            border-radius: 0 !important;
            color: var(--ink) !important;
            background: transparent !important;
            box-shadow: none !important;
            font-family: Inter, ui-sans-serif, system-ui, sans-serif !important;
            font-size: 20px !important;
            line-height: 1.45 !important;
            resize: none !important;
          }
          div[data-testid="stTextArea"] textarea::placeholder { color: #b5bad1; }
          [data-testid="InputInstructions"] { display: none !important; }
          [data-testid="stTextAreaRootElement"] { position: relative; }
          [data-testid="stTextAreaRootElement"]::before {
            content: "";
            position: absolute;
            top: 18px;
            left: 2px;
            width: 16px;
            height: 16px;
            border: 2px solid #6b7487;
            border-radius: 50%;
          }
          [data-testid="stTextAreaRootElement"]::after {
            content: "";
            position: absolute;
            top: 34px;
            left: 17px;
            width: 9px;
            height: 2px;
            border-radius: 99px;
            background: #6b7487;
            transform: rotate(45deg);
            transform-origin: left center;
          }
          div[data-testid="stFormSubmitButton"] { display: flex; justify-content: center; margin-top: 17px; }
          div[data-testid="stFormSubmitButton"] > button {
            width: 216px;
            min-height: 42px;
            border: 0;
            border-radius: 9px;
            color: #ffffff;
            background: var(--primary);
            font-size: 16px;
            font-weight: 650;
          }
          div[data-testid="stFormSubmitButton"] > button:hover { background: #241bc5; color: #ffffff; }
          .stButton { display: flex; justify-content: center; }
          .stButton > button {
            min-height: 38px;
            border: 1px solid var(--line);
            border-radius: 9px;
            color: #292d42;
            background: transparent;
            font-weight: 600;
          }
          .landing-state {
            max-width: 895px;
            margin: 76px auto 0;
            padding: 27px 29px;
            border: 1px solid #d5def0;
            border-radius: 14px;
            background: var(--soft-blue);
            font-family: Inter, ui-sans-serif, system-ui, sans-serif;
          }
          .landing-state .eyebrow {
            margin-bottom: 13px;
            color: #555d70;
            font-size: 14px;
            font-weight: 650;
            letter-spacing: .065em;
            text-transform: uppercase;
          }
          .landing-state h2 {
            margin: 0 0 8px;
            color: var(--ink);
            font-size: 22px;
            letter-spacing: -.025em;
          }
          .landing-state p { margin: 0; color: #4c566a; font-size: 16px; line-height: 1.55; }
          .submitted-question {
            margin: 18px 0 !important;
            padding: 13px 15px;
            border-radius: 9px;
            color: #17213a !important;
            background: rgba(255,255,255,.72);
          }
          .submitted-question span { color: #687287; font-size: 13px; font-weight: 650; text-transform: uppercase; letter-spacing: .055em; }
          .submitted-question strong { display: block; margin-top: 5px; font-weight: 600; }
          .notice {
            max-width: 895px;
            display: flex;
            align-items: flex-start;
            gap: 14px;
            margin: 76px auto 0;
            padding: 21px 20px;
            border: 1px solid #ffae88;
            border-radius: 10px;
            color: #a84219;
            background: #fff0e9;
            font-family: Inter, ui-sans-serif, system-ui, sans-serif;
          }
          .notice svg { flex: 0 0 auto; margin-top: 1px; }
          .notice p { margin: 0; font-size: 16px; line-height: 1.45; }

          @media (max-width: 760px) {
            [data-testid="stAppViewContainer"] > .main .block-container { padding: 0 16px 42px; }
            .top-nav { grid-template-columns: 1fr auto; padding: 0 18px; }
            .nav-links { display: none; }
            .brand { font-size: 20px; }
            .ask-hero { padding-top: 46px; }
            .ask-hero h1 { font-size: 32px; }
            [data-testid="stForm"], .landing-state, .notice { margin-top: 48px; }
            div[data-testid="stTextArea"] textarea { font-size: 17px !important; }
          }
        </style>

        <div class="ask-screen">
          <nav class="top-nav" aria-label="Primary navigation">
            <div class="brand">Ask Your Data</div>
            <div class="nav-links">
              <a class="nav-link active" href="#ask">Ask</a>
              <a class="nav-link" href="#my-data">My Data</a>
              <a class="nav-link" href="#settings">Settings</a>
            </div>
            <svg class="profile" viewBox="0 0 24 24" fill="none" aria-label="Profile">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
              <circle cx="12" cy="8.4" r="3" stroke="currentColor" stroke-width="1.8"/>
              <path d="M6.7 18.1c.8-2.6 2.6-4 5.3-4s4.5 1.4 5.3 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
          </nav>

          <section class="ask-hero" id="ask">
            <div class="chat-mark" aria-hidden="true">
              <svg width="38" height="38" viewBox="0 0 24 24" fill="none">
                <path d="M5.2 5.3h13.6v11.2H9.2l-4 3.2V5.3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
              </svg>
            </div>
            <h1>Ask anything about your data</h1>
            <p>Type a question to prepare it for your connected data source.</p>
          </section>
        </div>
        """
    )
)


with st.form("ask_data_form", border=False, enter_to_submit=False):
    question = st.text_area(
        "Your question",
        key="landing_question",
        height=58,
        placeholder="Type your question here...",
        label_visibility="collapsed",
    )
    submitted = st.form_submit_button("Get Answer  →", type="primary")

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
            <section class="landing-state" aria-live="polite">
              <div class="eyebrow">Question ready</div>
              <h2>Your question has been captured.</h2>
              <p class="submitted-question"><span>Your question</span><strong>{escape(submitted_question)}</strong></p>
              <p>No data source is connected yet, so there is no answer to display. Connect the query service to receive live, non-fabricated results.</p>
            </section>
            """
        )
    )
    st.button("Clear question", on_click=clear_question)
else:
    st.html(
        """
        <section class="landing-state" aria-live="polite">
          <div class="eyebrow">Live data status</div>
          <h2>Connect a data source to get answers.</h2>
          <p>This page accepts your question, but it will not invent a result, table, or source query while no data service is available.</p>
        </section>
        """
    )

st.html(
    """
    <aside class="notice" role="note">
      <svg width="25" height="25" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9.5" stroke="currentColor" stroke-width="1.8"/><path d="M12 10v5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="7" r="1.1" fill="currentColor"/></svg>
      <p>This tool is designed for read-only questions. Live answers will appear only when a connected data service returns them.</p>
    </aside>
    """
)
