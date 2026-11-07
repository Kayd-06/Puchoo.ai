"""Wrapper source contract; real Windows/PowerShell acceptance remains a release gate."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_powershell_migrates_from_application_root_and_restores_callers_directory():
    source = (ROOT / "scripts/migrate.ps1").read_text()
    assert "$RepoRoot = Split-Path -Parent $PSScriptRoot" in source
    assert "Push-Location $RepoRoot" in source
    assert "-m alembic -c backend/alembic.ini upgrade head" in source
    assert '"venv/Scripts/python.exe"' in source
    assert "finally" in source and "Pop-Location" in source
    assert "$LASTEXITCODE -ne 0" in source
    assert 'Set-Location (Join-Path' not in source
