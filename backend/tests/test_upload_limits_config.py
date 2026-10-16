"""Upload limit defaults stay conservative unless explicitly overridden."""

from backend.config import load_settings


def test_upload_max_files_defaults_to_ten(monkeypatch):
    monkeypatch.delenv("UPLOAD_MAX_FILES", raising=False)
    assert load_settings().upload_max_files == 10


def test_env_example_documents_ten_upload_files():
    from pathlib import Path

    example = (Path(__file__).resolve().parents[2] / ".env.example").read_text()
    assert "UPLOAD_MAX_FILES=10\n" in example
