"""In-process session store for development.

In production, this would be backed by Redis or a database.
"""

from typing import Any, Dict, List, Optional

class SessionManager:
    def __init__(self) -> None:
        self.workspaces: Dict[str, Dict[str, Any]] = {}
        self.workspace_guardrails: Dict[str, Dict[str, Any]] = {}
        self.query_history: Dict[str, List[Dict[str, Any]]] = {}
        self.schema_snapshots: Dict[str, str] = {}
        self.active_proposals: Dict[str, Dict[str, Any]] = {}

        # New state for multi-tier RBAC and users
        # users: Dict[email, Dict[str, Any]]
        self.users: Dict[str, Dict[str, Any]] = {}
        
        # workspace_members: Dict[workspace_id, Dict[email, role]]
        self.workspace_members: Dict[str, Dict[str, str]] = {}
        
        # invites: Dict[invite_code, Dict[str, str]] (e.g., {"code123": {"workspace_id": "ws-1", "role": "editor"}})
        self.invites: Dict[str, Dict[str, str]] = {}
        
        # otps: Dict[identifier, otp_code]
        self.otps: Dict[str, str] = {}

    def set_otp(self, identifier: str, otp_code: str) -> None:
        self.otps[identifier] = otp_code
        
    def verify_otp(self, identifier: str, otp_code: str) -> bool:
        if self.otps.get(identifier) == otp_code:
            # Consume the OTP after verification
            del self.otps[identifier]
            return True
        return False

    def get_workspace(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        return self.workspaces.get(workspace_id)

    def add_workspace(self, workspace: Dict[str, Any], creator_email: str) -> None:
        ws_id = workspace["id"]
        self.workspaces[ws_id] = workspace
        self.workspace_guardrails.setdefault(ws_id, {
            "max_rows": 500,
            "timeout_seconds": 30,
            "confirm_complex_queries": False
        })
        self.query_history.setdefault(ws_id, [])
        self.workspace_members[ws_id] = {creator_email: "admin"}

    def remove_workspace(self, workspace_id: str) -> None:
        self.workspaces.pop(workspace_id, None)
        self.workspace_guardrails.pop(workspace_id, None)
        self.query_history.pop(workspace_id, None)
        self.schema_snapshots.pop(f"schema_{workspace_id}", None)
        self.active_proposals.pop(workspace_id, None)
        self.workspace_members.pop(workspace_id, None)

    def add_user(self, email: str, name: str, account_type: str = "personal") -> None:
        if email not in self.users:
            self.users[email] = {
                "name": name,
                "email": email,
                "account_type": account_type,
                "department": "Operations",
                "timezone": "UTC"
            }

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        return self.users.get(email)

    def get_user_workspaces(self, email: str) -> List[Dict[str, Any]]:
        user_ws = []
        for ws_id, members in self.workspace_members.items():
            if email in members:
                ws = self.workspaces.get(ws_id)
                if ws:
                    ws_copy = ws.copy()
                    ws_copy["user_role"] = members[email]
                    user_ws.append(ws_copy)
        return user_ws

    def create_invite(self, workspace_id: str, code: str, role: str) -> None:
        self.invites[code] = {
            "workspace_id": workspace_id,
            "role": role
        }

    def join_workspace(self, email: str, code: str) -> bool:
        if code in self.invites:
            invite = self.invites[code]
            ws_id = invite["workspace_id"]
            role = invite["role"]
            if ws_id in self.workspaces:
                self.workspace_members.setdefault(ws_id, {})
                self.workspace_members[ws_id][email] = role
                return True
        return False

# Global singleton for the development server
session_manager = SessionManager()
