"""Unit tests for the Groq client wrapper without making network calls."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from apps.core.llm_client import LLMClient, SQLGenerationError, build_prompt


class _FakeCompletions:
    def __init__(self, content: str | None) -> None:
        self.content = content
        self.kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


class _FakeClient:
    def __init__(self, content: str | None) -> None:
        self.completions = _FakeCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


class LLMClientTests(unittest.TestCase):
    def test_prompt_keeps_schema_and_question_as_json_data(self) -> None:
        prompt = build_prompt("Table: orders", "Show revenue")
        self.assertEqual("system", prompt.messages[0]["role"])
        self.assertIn('"schema": "Table: orders"', prompt.messages[1]["content"])
        self.assertIn('"question": "Show revenue"', prompt.messages[1]["content"])

    def test_client_uses_groq_chat_completion_and_returns_sql(self) -> None:
        fake_client = _FakeClient("```sql\nSELECT id FROM orders\n```")
        client = LLMClient(client=fake_client, model="test-model")
        sql = client.generate_sql(schema="Table: orders", question="List ids")
        self.assertEqual("SELECT id FROM orders", sql)
        self.assertEqual("test-model", fake_client.completions.kwargs["model"])
        self.assertEqual(0, fake_client.completions.kwargs["temperature"])

    def test_empty_model_response_is_rejected(self) -> None:
        client = LLMClient(client=_FakeClient(None))
        with self.assertRaises(SQLGenerationError):
            client.generate_sql(schema="Table: orders", question="List ids")
