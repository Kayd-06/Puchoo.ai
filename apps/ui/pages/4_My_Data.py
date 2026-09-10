from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.core.workspaces import (
    create_server_workspace,
    create_sqlite_workspace,
    create_tabular_workspace,
    create_uploaded_sqlite_workspace,
    get_schema_metrics,
    get_schema_snapshot,
    get_schema_table_stats,
)
from apps.ui.components.app_shell import active_workspace, initialize_app, page_header, persist_app_state


def activate_workspace(workspace: object) -> None:
    """Make a successfully validated workspace active in this browser session."""

    workspace_data = workspace.as_dict()  # type: ignore[attr-defined]
    st.session_state.workspaces[workspace_data["id"]] = workspace_data
    st.session_state.workspace_guardrails.setdefault(workspace_data["id"], {})
    st.session_state.query_history.setdefault(workspace_data["id"], [])
    st.session_state.active_workspace_id = workspace_data["id"]
    st.session_state.active_proposal = None
    persist_app_state()


initialize_app("My Data")
page_header(
    "Workspace ingestion",
    "Connect your data",
    "Upload a CSV or Excel workbook, or connect a PostgreSQL/MySQL server. Pucho reads approved sources in read-only mode.",
)

st.markdown(
    '<div class="surface-card"><span class="status status-ok">READ-ONLY SAFETY GUARANTEE</span>'
    '<h4 style="margin:.55rem 0 .25rem;color:#102044;">Your source data cannot be changed.</h4>'
    '<div class="muted">Write statements are rejected before execution, result sets are bounded, and each supported database receives an additional read-only connection setting.</div></div>',
    unsafe_allow_html=True,
)
st.write("")

file_tab, server_tab, sqlite_tab = st.tabs(["Upload CSV or Excel", "Connect database server", "SQLite file"])

with file_tab:
    st.subheader("Local spreadsheet importer")
    st.caption("CSV files become one queryable table. Each non-empty Excel sheet becomes its own table. The local workspace remains available after browser refresh.")
    tabular_upload = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        key="tabular_file",
        help="Supported formats: .csv, .xlsx, and .xls.",
    )
    import_name = st.text_input("Workspace name", placeholder="Defaults to the uploaded file name", key="tabular_workspace_name")
    if st.button("Create workspace from file", type="primary", disabled=tabular_upload is None):
        if tabular_upload is not None:
            try:
                workspace = create_tabular_workspace(
                    import_name.strip() or Path(tabular_upload.name).stem,
                    tabular_upload.name,
                    tabular_upload.getvalue(),
                )
                activate_workspace(workspace)
                st.success(f"{workspace.name} is ready for read-only questions.")
            except ValueError as exc:
                st.error(str(exc))

with server_tab:
    st.subheader("Connect a database server")
    st.caption("Use a dedicated database account that has read-only permissions. Credentials remain only in this running app session and are used to validate the schema before saving the workspace.")
    with st.form("server_connection"):
        server_name = st.text_input("Workspace name", placeholder="e.g. Production analytics")
        engine = st.selectbox("Database engine", ["PostgreSQL", "MySQL"])
        host, port = st.columns([3, 1])
        with host:
            server_host = st.text_input("Host", placeholder="db.example.com")
        with port:
            server_port = st.number_input("Port", min_value=1, max_value=65535, value=5432 if engine == "PostgreSQL" else 3306, step=1)
        database_name = st.text_input("Database name")
        username, password = st.columns(2)
        with username:
            server_username = st.text_input("Read-only username")
        with password:
            server_password = st.text_input("Password", type="password")
        ssl_required = st.checkbox("Require encrypted TLS connection", value=True)
        server_submitted = st.form_submit_button("Validate and connect server", type="primary")
    if server_submitted:
        try:
            if not server_password:
                raise ValueError("Password is required. Use a dedicated read-only database account.")
            workspace = create_server_workspace(
                server_name,
                engine="postgresql" if engine == "PostgreSQL" else "mysql",
                host=server_host,
                port=int(server_port),
                database=database_name,
                username=server_username,
                password=server_password,
                ssl_required=ssl_required,
            )
            activate_workspace(workspace)
            st.success(f"{workspace.name} is connected and ready for read-only questions.")
        except ValueError as exc:
            st.error(str(exc))

with sqlite_tab:
    st.subheader("Existing SQLite database")
    st.caption("For an existing .db/.sqlite file, upload it or provide its local path. Local sources remain available after browser refresh.")
    sqlite_upload = st.file_uploader("Upload a SQLite database", type=["db", "sqlite", "sqlite3"], key="sqlite_file")
    if sqlite_upload and st.button("Connect uploaded SQLite database", type="primary"):
        try:
            workspace = create_uploaded_sqlite_workspace(Path(sqlite_upload.name).stem, sqlite_upload.name, sqlite_upload.getvalue())
            activate_workspace(workspace)
            st.success(f"{workspace.name} is ready for read-only questions.")
        except ValueError as exc:
            st.error(str(exc))

    with st.form("existing_sqlite_workspace", clear_on_submit=False):
        local_name = st.text_input("Workspace name", placeholder="e.g. Product analytics", key="sqlite_workspace_name")
        database_path = st.text_input("SQLite database file", placeholder="/absolute/path/to/analytics.db")
        local_submitted = st.form_submit_button("Connect local SQLite file")
    if local_submitted:
        try:
            workspace = create_sqlite_workspace(local_name, database_path)
            activate_workspace(workspace)
            st.success(f"{workspace.name} is ready.")
        except ValueError as exc:
            st.error(str(exc))

workspace = active_workspace()
if workspace:
    st.divider()
    with st.container(border=True):
        st.markdown("<span class='status status-ok'>CONNECTED &amp; INSPECTED</span>", unsafe_allow_html=True)
        st.subheader(workspace["name"])
        source_label = {"spreadsheet": "CSV / Excel workspace", "server": "Database server", "file": "SQLite file"}.get(workspace.get("source_type"), "Data source")
        st.caption(f"{source_label} · all values below are read from the currently connected source. No sample records are used.")
        try:
            metrics = get_schema_metrics(workspace["database_uri"])
            local_source = workspace.get("source_type") in {"spreadsheet", "file"}
            table_stats = get_schema_table_stats(workspace["database_uri"], include_row_counts=local_source)
            stat_one, stat_two, stat_three = st.columns(3)
            stat_one.metric("Tables indexed", metrics["tables"])
            stat_two.metric("Columns available", metrics["columns"])
            if local_source:
                stat_three.metric("Source rows", sum(int(table["rows"] or 0) for table in table_stats))
            else:
                stat_three.metric("Source rows", "Not counted")
                st.caption("Row totals are intentionally not scanned on a database server because a full count can be expensive. Table and column metadata is live.")
            table_chips = " · ".join(
                f"{table['name']} ({table['rows']:,} rows)" if table["rows"] is not None else str(table["name"])
                for table in table_stats
            )
            st.caption(f"Live tables: {table_chips}")
        except ValueError as exc:
            st.error(str(exc))
        if st.button("Refresh live schema"):
            try:
                st.session_state[f"schema_{workspace['id']}"] = get_schema_snapshot(workspace["database_uri"])
                st.success("Live schema refreshed from the connected source.")
            except ValueError as exc:
                st.error(str(exc))
        try:
            schema = st.session_state.get(f"schema_{workspace['id']}") or get_schema_snapshot(workspace["database_uri"])
            with st.expander("View live schema"):
                st.code(schema, language="text")
        except ValueError as exc:
            st.error(str(exc))
