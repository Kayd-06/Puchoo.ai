"""UI-only data source setup for the Pucho.ai workspace."""

from __future__ import annotations

from html import escape
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import streamlit as st

from components.app_shell import badge, configure_page


configure_page("My data", ":material/storage:")


def format_file_size(size: int | None) -> str:
    """Return a compact, human-readable file size without inspecting file content."""
    if not size:
        return "Size unavailable"

    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "Size unavailable"


def save_server_configuration() -> None:
    """Keep non-sensitive connection metadata locally; never store the password."""
    required_fields = {
        "Connection name": "my_data_connection_name",
        "Host": "my_data_server_host",
        "Database": "my_data_server_database",
        "Username": "my_data_server_username",
        "Password": "my_data_server_password",
    }
    missing = [
        label
        for label, key in required_fields.items()
        if not str(st.session_state.get(key, "")).strip()
    ]
    if missing:
        st.session_state["my_data_connection_feedback"] = (
            "error",
            f"Complete {', '.join(missing)} before saving the configuration.",
        )
        return

    st.session_state["my_data_server_draft"] = {
        "name": st.session_state["my_data_connection_name"].strip(),
        "type": st.session_state["my_data_server_type"],
        "host": st.session_state["my_data_server_host"].strip(),
        "port": int(st.session_state["my_data_server_port"]),
        "database": st.session_state["my_data_server_database"].strip(),
        "username": st.session_state["my_data_server_username"].strip(),
        "ssl": bool(st.session_state["my_data_server_ssl"]),
    }
    st.session_state["my_data_server_password"] = ""
    st.session_state["my_data_connection_feedback"] = (
        "success",
        "Connection details are ready for review. No server request was made.",
    )


def forget_upload() -> None:
    st.session_state.pop("my_data_upload_draft", None)


def forget_server_configuration() -> None:
    st.session_state.pop("my_data_server_draft", None)
    st.session_state.pop("my_data_connection_feedback", None)


st.html(
    """
    <style>
      [data-testid="stTabs"] { margin-top: 1.5rem; }
      [data-testid="stTabs"] button { color: #737373 !important; font-weight: 650 !important; }
      [data-testid="stTabs"] button[aria-selected="true"] { color: #171717 !important; }
      [data-testid="stFileUploaderDropzone"] {
        min-height: 176px;
        border: 1px dashed #a3a3a3 !important;
        border-radius: 12px !important;
        background: #ffffff !important;
      }
      [data-testid="stFileUploaderDropzone"]:hover {
        border-color: #171717 !important;
        background: #fafafa !important;
      }
      [data-testid="stFileUploaderDropzone"] button {
        border: 1px solid #d4d4d4 !important;
        border-radius: 8px !important;
        color: #171717 !important;
        background: #ffffff !important;
      }
      [data-testid="stFileUploaderDropzone"] button:hover { background: #f5f5f5 !important; }
      .my-data-intro { max-width: 620px; }
      .my-data-intro p { margin: .45rem 0 0; color: #737373; line-height: 1.6; }
      .my-data-note {
        margin-top: .95rem;
        padding-left: .8rem;
        border-left: 2px solid #d4d4d4;
        color: #737373;
        font-size: .84rem;
        line-height: 1.5;
      }
    </style>
    <div class="my-data-intro">
      <div class="pucho-eyebrow">Data sources</div>
      <h1>My data</h1>
      <p>Add a file or prepare a server connection. This prototype does not import data or contact a server.</p>
    </div>
    """
)

upload_tab, server_tab = st.tabs(["Upload a file", "Connect a server"])

with upload_tab:
    st.markdown("### Add a file")
    st.caption("CSV, Excel, JSON, and Parquet files are supported by the future import service.")
    with st.form("my_data_upload_form", border=False, clear_on_submit=False):
        uploaded_file = st.file_uploader(
            "Upload a data file",
            type=["csv", "xlsx", "xls", "json", "parquet"],
            key="my_data_file",
            help="Selecting a file only stages its name and size for this local session.",
        )
        source_name = st.text_input(
            "Source name",
            key="my_data_source_name",
            placeholder="For example: September sales",
        )
        source_description = st.text_area(
            "What does this data contain? (optional)",
            key="my_data_source_description",
            placeholder="For example: Orders, customers, and revenue by day.",
            height=92,
        )
        upload_submitted = st.form_submit_button(
            "Add file",
            type="primary",
            icon=":material/add:",
            use_container_width=True,
        )

    if upload_submitted:
        if uploaded_file is None:
            st.error("Choose a file before adding it.", icon=":material/error:")
        else:
            filename = uploaded_file.name
            default_name = Path(filename).stem.replace("_", " ").strip()
            st.session_state["my_data_upload_draft"] = {
                "name": source_name.strip() or default_name or "Untitled source",
                "filename": filename,
                "description": source_description.strip(),
                "size": uploaded_file.size,
            }
            st.success(
                "File added locally for this session. It has not been imported yet.",
                icon=":material/check_circle:",
            )

    st.html(
        """
        <div class="my-data-note">
          File contents are not previewed, parsed, or sent anywhere in this UI-only version.
        </div>
        """
    )

with server_tab:
    st.markdown("### Prepare a server connection")
    st.caption("Save the connection shape now; a future service will validate and connect it securely.")
    with st.form("my_data_server_form", border=False, clear_on_submit=False):
        server_type = st.selectbox(
            "Server type",
            ["PostgreSQL", "MySQL", "Microsoft SQL Server", "Snowflake", "Other"],
            key="my_data_server_type",
        )
        connection_name = st.text_input(
            "Connection name",
            key="my_data_connection_name",
            placeholder="For example: Production analytics",
        )
        host_column, port_column = st.columns([1.5, .7])
        with host_column:
            host = st.text_input(
                "Host",
                key="my_data_server_host",
                placeholder="db.example.com",
                help="Use a hostname or private network address. No connection is attempted here.",
            )
        with port_column:
            port = st.number_input(
                "Port",
                min_value=1,
                max_value=65_535,
                value=5432,
                step=1,
                key="my_data_server_port",
            )
        database_column, username_column = st.columns(2)
        with database_column:
            database = st.text_input(
                "Database",
                key="my_data_server_database",
                placeholder="analytics",
            )
        with username_column:
            username = st.text_input(
                "Username",
                key="my_data_server_username",
                placeholder="analytics_reader",
            )
        password = st.text_input(
            "Password",
            type="password",
            key="my_data_server_password",
            help="This value is cleared after configuration is saved and is never shown in the source summary.",
        )
        ssl = st.checkbox(
            "Use an encrypted connection (SSL/TLS)",
            value=True,
            key="my_data_server_ssl",
        )
        st.form_submit_button(
            "Save connection details",
            type="primary",
            icon=":material/lock:",
            use_container_width=True,
            on_click=save_server_configuration,
        )

    connection_feedback = st.session_state.get("my_data_connection_feedback")
    if connection_feedback:
        level, message = connection_feedback
        if level == "error":
            st.error(message, icon=":material/error:")
        else:
            st.success(message, icon=":material/check_circle:")

    st.html(
        """
        <div class="my-data-note">
          Passwords are not retained in the saved connection summary, and this page never sends a network request.
        </div>
        """
    )

st.markdown('<hr class="pucho-rule">', unsafe_allow_html=True)
st.markdown("### Added sources")

upload_draft = st.session_state.get("my_data_upload_draft")
server_draft = st.session_state.get("my_data_server_draft")

if not upload_draft and not server_draft:
    st.caption("No sources are staged yet. Choose one of the options above to begin.")

if upload_draft:
    details_column, status_column, action_column = st.columns([2.2, 1, .55], vertical_alignment="center")
    with details_column:
        st.markdown(f"**{escape(upload_draft['name'])}**")
        detail = f"File · {escape(upload_draft['filename'])} · {format_file_size(upload_draft['size'])}"
        if upload_draft["description"]:
            detail = f"{detail} · {escape(upload_draft['description'])}"
        st.caption(detail)
    with status_column:
        badge("Ready to import", "neutral")
    with action_column:
        st.button("Remove", key="remove_staged_file", width="stretch", on_click=forget_upload)

if server_draft:
    details_column, status_column, action_column = st.columns([2.2, 1, .55], vertical_alignment="center")
    with details_column:
        st.markdown(f"**{escape(server_draft['name'])}**")
        encrypted = "SSL/TLS" if server_draft["ssl"] else "No SSL/TLS"
        st.caption(
            f"{escape(server_draft['type'])} · {escape(server_draft['host'])}:{server_draft['port']} · "
            f"{escape(server_draft['database'])} · {encrypted}"
        )
    with status_column:
        badge("Ready to connect", "neutral")
    with action_column:
        st.button(
            "Remove",
            key="remove_server_configuration",
            width="stretch",
            on_click=forget_server_configuration,
        )
