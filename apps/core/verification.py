"""Independent describe-and-compare verification for executed SQL results."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Protocol


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    VERIFICATION_MISMATCH = "VERIFICATION_MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    confidence: int | None
    summary: str
    details: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "status": self.status.value}


class ClaudeClient(Protocol):
    @property
    def messages(self) -> Any: ...


class GroqClient(Protocol):
    def _chat(self, *, system: str, user: str, max_tokens: int | None = None,
              response_format: dict[str, Any] | None = None, model: str | None = None) -> str: ...


VERIFY_SYSTEM_PROMPT = """You are an independent analytics verifier. Compare the user question,
executed read-only SQL, and returned rows. Do not assume the SQL is correct.
Return JSON only with: verdict (MATCH or MISMATCH), confidence (integer 0-100),
summary (short factual description), and details (short reason). A MATCH means
the query and results answer the question within the available data; otherwise
return MISMATCH."""


def _result_payload(columns: list[str], rows: list[dict[str, Any]], row_count: int) -> dict[str, Any]:
    # Verification needs enough evidence to catch semantic errors, but a bounded
    # sample prevents large result sets from becoming an unbounded prompt.
    return {"columns": columns, "row_count": row_count, "rows": rows[:50]}


def _verification_from_content(content: str) -> VerificationResult:
    """Parse either provider's JSON-only verifier response."""

    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    parsed = json.loads(cleaned.strip())
    verdict = str(parsed.get("verdict", "")).upper()
    confidence = int(parsed.get("confidence"))
    if not 0 <= confidence <= 100 or verdict not in {"MATCH", "MISMATCH"}:
        raise ValueError("Verifier returned an invalid verdict.")
    return VerificationResult(
        status=VerificationStatus.VERIFIED if verdict == "MATCH" else VerificationStatus.VERIFICATION_MISMATCH,
        confidence=confidence,
        summary=str(parsed.get("summary") or "Verification completed."),
        details=str(parsed.get("details") or "") or None,
    )


class ClaudeVerifier:
    """Second-model verifier. It never runs SQL and never mutates a workspace."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None, client: ClaudeClient | None = None) -> None:
        if client is None:
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass
        self.model = model or os.getenv("ANTHROPIC_VERIFIER_MODEL", "claude-haiku-4-5-20251001")
        if client is not None:
            self._client = client
            return
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("The anthropic SDK is not installed.") from exc
        self._client = Anthropic(api_key=key)

    def verify(self, *, question: str, sql: str, columns: list[str], rows: list[dict[str, Any]], row_count: int) -> VerificationResult:
        payload = json.dumps(
            {"question": question, "sql": sql, "result": _result_payload(columns, rows, row_count)},
            default=str,
            ensure_ascii=False,
        )
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=500,
                system=VERIFY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": payload}],
            )
            return _verification_from_content(response.content[0].text)
        except Exception as exc:
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                confidence=None,
                summary="Independent verification is unavailable.",
                details=str(exc),
            )


class GroqVerifier:
    """Groq fallback for post-execution verification when Anthropic is not configured."""

    def __init__(self, *, model: str | None = None, client: GroqClient | None = None) -> None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        self.model = model or os.getenv("GROQ_VERIFIER_MODEL") or os.getenv("GROQ_MODEL")
        if client is not None:
            self._client = client
            return
        from apps.core.llm_client import GroqSQLClient
        self._client = GroqSQLClient(model=self.model)

    def verify(self, *, question: str, sql: str, columns: list[str], rows: list[dict[str, Any]], row_count: int) -> VerificationResult:
        payload = json.dumps(
            {"question": question, "sql": sql, "result": _result_payload(columns, rows, row_count)},
            default=str,
            ensure_ascii=False,
        )
        try:
            content = self._client._chat(
                system=VERIFY_SYSTEM_PROMPT,
                user=payload,
                max_tokens=500,
                response_format={"type": "json_object"},
                model=self.model,
            )
            return _verification_from_content(content)
        except Exception as exc:
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                confidence=None,
                summary="Independent verification is unavailable.",
                details=str(exc),
            )


def get_verifier() -> ClaudeVerifier | GroqVerifier:
    """Prefer an independent Anthropic check; otherwise use the configured Groq client."""

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    if os.getenv("ANTHROPIC_API_KEY"):
        return ClaudeVerifier()
    return GroqVerifier()


def verification_unavailable(reason: str) -> VerificationResult:
    return VerificationResult(VerificationStatus.UNAVAILABLE, None, "Independent verification is unavailable.", reason)
