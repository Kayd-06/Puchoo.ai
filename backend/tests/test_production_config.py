"""Production must refuse to start without secure cookies."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.config import ensure_production_cookie_security

ROOT = Path(__file__).resolve().parents[2]


def test_production_requires_secure_cookies():
    with pytest.raises(RuntimeError, match="COOKIE_SECURE must be true"):
        ensure_production_cookie_security("production", False)
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        ensure_production_cookie_security(" Production ", False)
    ensure_production_cookie_security("production", True)
    ensure_production_cookie_security("development", False)


@pytest.mark.parametrize("cookie_secure,ok", [("false", False), ("", False), ("true", True)])
def test_config_import_enforces_secure_cookies_in_production(cookie_secure, ok, tmp_path):
    env = {
        **os.environ,
        "ENVIRONMENT": "production",
        "COOKIE_SECURE": cookie_secure,
        "SESSION_SECRET": "unique-session-secret-for-test",
        "OTP_SECRET": "unique-otp-secret-for-test",
        "DATABASE_URL": "sqlite:///" + (tmp_path / "t.db").as_posix(),
    }
    result = subprocess.run(
        [sys.executable, "-c", "import backend.config"], cwd=ROOT, env=env, capture_output=True, text=True
    )
    if ok:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert "COOKIE_SECURE must be true" in result.stderr
