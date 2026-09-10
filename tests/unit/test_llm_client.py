"""Unit tests for the Claude SQL client without making network calls."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from apps.core.llm_client import LLMClient, SQLGenerationError, build_prompt


class _FakeMessages:
    def __init__(self, content: str | None) -> None:
        self.content = content
        self.kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(text=self.content)])


class _FakeClient:
    def __init__(self, content: str | None) -> None:
        self.messages = _FakeMessages(content)


class LLMClientTests(unittest.TestCase):
    def test_prompt_keeps_schema_and_question_as_json_data(self) -> None:
        prompt = build_prompt("Table: orders", "Show revenue")
        self.assertIn("read-only SQL", prompt.system)
        self.assertEqual("user", prompt.messages[0]["role"])
        self.assertIn('"schema": "Table: orders"', prompt.messages[0]["content"])
        self.assertIn('"question": "Show revenue"', prompt.messages[0]["content"])

    def test_client_uses_claude_messages_and_returns_sql(self) -> None:
        fake_client = _FakeClient("```sql\nSELECT id FROM orders\n```")
        client = LLMClient(client=fake_client, model="test-model")
        sql = client.generate_sql(schema="Table: orders", question="List ids")
        self.assertEqual("SELECT id FROM orders", sql)
        self.assertEqual("test-model", fake_client.messages.kwargs["model"])
        self.assertIn("system", fake_client.messages.kwargs)

    def test_empty_model_response_is_rejected(self) -> None:
        client = LLMClient(client=_FakeClient(None))
        with self.assertRaises(SQLGenerationError):
            client.generate_sql(schema="Table: orders", question="List ids")
