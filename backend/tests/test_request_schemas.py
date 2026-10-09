"""Public request models reject coercion, unknown fields, and abusive sizes."""

import pytest
from pydantic import ValidationError

from apps.api.routers.query import ApproveRequest, GenerateRequest
from apps.api.routers.settings import GuardrailsRequest
from apps.api.routers.workspaces import ServerWorkspaceRequest
from backend.schemas import LoginRequest, SignupRequest


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (LoginRequest, {"email": "person@example.com", "password": "valid-password", "admin": True}),
        (LoginRequest, {"email": "person@example.com", "password": "x" * 1_025}),
        (SignupRequest, {"full_name": "A", "email": "person@example.com", "password": "password10", "confirm_password": "password10", "workspace_type": "personal", "unknown": "value"}),
        (GenerateRequest, {"question": "x" * 4_001}),
        (ApproveRequest, {"sql_hash": "../unsafe"}),
        (ApproveRequest, {"sql_hash": "a" * 64, "sql": "SELECT 1"}),
        (GuardrailsRequest, {"max_rows": 0, "timeout_seconds": 30, "confirm_complex_queries": True}),
        (ServerWorkspaceRequest, {"name": "DB", "engine": "postgresql", "host": "db.example.com", "port": "5432", "database": "app", "username": "user", "password": "secret"}),
    ],
)
def test_request_models_reject_invalid_boundaries(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)
