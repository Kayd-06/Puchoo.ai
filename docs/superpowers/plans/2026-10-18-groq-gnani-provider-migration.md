# Groq and Gnani Provider Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Groq the only language-model provider and Gnani the only speech-to-text provider while preserving query safety, multilingual input, and voice recording UX.

**Architecture:** The existing OpenAI-compatible Groq adapter becomes the sole client for query planning, SQL generation, repair, verification, and on-demand input translation. A new server-side Gnani REST adapter accepts validated browser audio via a `/api/voice/transcribe` boundary. Claude, local MLX, and Sarvam are deleted rather than retained as selectable fallbacks.

**Tech Stack:** FastAPI, Python standard-library HTTP client, Pydantic, pytest, React, Vitest, Vite.

**Spec:** `docs/superpowers/specs/2026-10-18-groq-gnani-provider-migration.md`

## Global Constraints

- Never add or log a production `GROQ_API_KEY` or `GNANI_API_KEY`; use only untracked local `.env` configuration.
- Support Indian English, Hindi, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi, and Odia through Gnani automatic STT detection.
- Translate only non-English question input before SQL planning; summaries, labels, and returned cells remain English.
- Do not change SQL parsing, read-only execution, query approval, schema reduction, or authorization boundaries.
- Do not retain Claude, Anthropic, local-MLX, or Sarvam compatibility paths, dependencies, settings, routes, or UI copy.
- Use no Gnani SDK dependency; use the documented Gnani REST multipart API from the backend so application dependencies stay minimal.

## Review Focus

- A missing or rejected Groq key must stop query generation safely and never fall back to Claude or a local model. Covered in Task 1.
- A non-English question must make exactly one bounded translation request before planning, preserving numbers and quoted values. Covered in Task 1 and Task 3.
- Gnani must not receive unvalidated, oversized, or falsely named audio. Covered in Task 2.
- A Gnani failure response or malformed success payload must not leak provider details or keys to the browser. Covered in Task 2.
- Browser recordings and role checks must continue to use the protected voice endpoint after the route rename. Covered in Task 3.

---

### Task 1: Make Groq the sole language-model boundary

**Files:**
- Modify: `apps/core/llm_client.py`
- Modify: `apps/core/verification.py`
- Modify: `apps/api/routers/query.py`
- Modify: `tests/unit/test_llm_client.py`
- Modify: `tests/unit/test_verification.py`

**Interfaces:**
- Produces `GroqConfigurationError(RuntimeError)` and a standalone `GroqSQLClient` with `generate_plan`, `generate_sql`, `_chat`, and `translate_to_english(text: str, source_language: str) -> str`.
- Produces `get_sql_client() -> GroqSQLClient` and `get_verifier() -> GroqVerifier` with no provider selection branch.
- Consumes the existing `SQLGenerationError`, query-planning prompts, and `GROQ_*` environment values.

- [ ] **Step 1: Write failing Groq-only tests**

Add tests that assert `get_sql_client()` rejects a missing `GROQ_API_KEY`, returns `GroqSQLClient` when set, and never accepts `PUCHOO_SQL_PROVIDER=claude` or `local`. Add a translation test that inspects the fake HTTP request: it uses the configured translation model, max tokens are at most `GROQ_TRANSLATION_MAX_TOKENS`, and the result strips no numeric or quoted literal from the input payload.

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `pytest tests/unit/test_llm_client.py tests/unit/test_verification.py -q`

Expected: FAIL because factory branches and Claude/local clients still exist, and `translate_to_english` is absent.

- [ ] **Step 3: Refactor `apps/core/llm_client.py` to Groq-only classes**

Delete `LLMClient`, `ClaudeClient`, `LocalMLXSQLClient`, `AnthropicConfigurationError`, `LocalMLXConfigurationError`, the local endpoint constants, and compatibility aliases. Make `GroqSQLClient` independent rather than a local-client subclass; preserve its request safety headers, zero temperature, strict planner JSON schema, SQL extraction, and repair interface. Introduce `GroqConfigurationError` for missing/failed Groq configuration and add:

```python
def translate_to_english(self, text: str, source_language: str) -> str:
    ...
```

Use a JSON-only Groq request with a translation-specific system prompt, `GROQ_TRANSLATION_MODEL` falling back to `GROQ_MODEL`, and a clamped `GROQ_TRANSLATION_MAX_TOKENS` default of 320. Reject an empty/malformed translation response.

- [ ] **Step 4: Make verification and query repair Groq-only**

Delete `ClaudeVerifier` and its protocol from `apps/core/verification.py`; `get_verifier()` always constructs `GroqVerifier`. In `apps/api/routers/query.py`, replace local-client type checks with Groq capability use, apply the existing bounded retry/repair behavior to Groq, and catch `GroqConfigurationError` in the existing safe error paths.

- [ ] **Step 5: Run targeted tests to verify they pass**

Run: `pytest tests/unit/test_llm_client.py tests/unit/test_verification.py backend/tests/test_query_approval.py -q`

Expected: PASS, including Groq-only construction, bounded translation, verifier JSON parsing, and existing approval/guardrail coverage.

- [ ] **Step 6: Commit the Groq-only provider boundary**

```bash
git add apps/core/llm_client.py apps/core/verification.py apps/api/routers/query.py tests/unit/test_llm_client.py tests/unit/test_verification.py backend/tests/test_query_approval.py
git commit -m "refactor: make Groq the only query provider"
```

### Task 2: Add the Gnani STT boundary

**Files:**
- Create: `apps/core/gnani_client.py`
- Create: `apps/api/routers/voice.py`
- Create: `tests/unit/test_gnani_client.py`
- Create: `backend/tests/test_voice_security.py`
- Modify: `backend/tests/test_sarvam_audio.py` → rename to `backend/tests/test_voice_audio.py`
- Modify: `backend/main.py`
- Modify: `apps/api/security.py`

**Interfaces:**
- Produces `GnaniConfigurationError(RuntimeError)`, `TranscriptionResult(transcript: str, language_code: str | None)`, and `GnaniClient.transcribe(audio: bytes, filename: str, *, language_code: str = "auto") -> TranscriptionResult`.
- Produces `POST /api/voice/transcribe` returning `{"transcript": str, "language_code": str | None}`.
- Consumes the existing authenticated upload limit from `backend.config.settings.upload_max_bytes` and the browser’s validated filename.

- [ ] **Step 1: Write failing Gnani adapter tests**

Add fake-`urlopen` tests that require `X-API-Key-ID`, multipart `audio_file`, `language_code=auto`, `preferred_language`, and `format=transcribe`. Add failure tests for missing key, missing/blank `transcript`, an HTTP error, and a transport error; no exception message may contain the upstream body or API key.

- [ ] **Step 2: Run the new unit tests to verify they fail**

Run: `pytest tests/unit/test_gnani_client.py -q`

Expected: FAIL because `apps.core.gnani_client` does not exist.

- [ ] **Step 3: Implement `GnaniClient` with multipart REST transport**

In `apps/core/gnani_client.py`, load dotenv only when no explicit fake key/client is supplied, require `GNANI_API_KEY`, and construct a bounded in-memory multipart body with the original filename. Call Gnani’s STT REST endpoint with the documented `X-API-Key-ID` header. Parse only a non-empty `transcript`; normalize optional BCP-47 `language_code` and otherwise return `None`.

- [ ] **Step 4: Write failing protected-route and audio-validation tests**

Move the current Safari m4a/mp4 signature test to `backend/tests/test_voice_audio.py`. Add an authenticated route test that fakes `GnaniClient` failure and expects exactly `502` with `"Transcription is temporarily unavailable."`; add a role test that a viewer cannot call `/api/voice/transcribe`.

- [ ] **Step 5: Run route tests to verify they fail**

Run: `pytest backend/tests/test_voice_audio.py backend/tests/test_voice_security.py backend/tests/test_role_access.py -q`

Expected: FAIL because the voice router is not registered and the new endpoint is absent.

- [ ] **Step 6: Implement `apps/api/routers/voice.py` and register it**

Move `_read_audio` and its existing signatures into the voice router unchanged. Gate `/transcribe` with `require_capability("query_workspace")`, call `GnaniClient.transcribe`, map missing configuration to 503, and map every external failure to the fixed 502 response. Register `voice.router` under `/api` in `backend/main.py`; update the CSRF upload exception to `/api/voice/transcribe`.

- [ ] **Step 7: Run Gnani and route tests to verify they pass**

Run: `pytest tests/unit/test_gnani_client.py backend/tests/test_voice_audio.py backend/tests/test_voice_security.py backend/tests/test_role_access.py -q`

Expected: PASS, with no provider details exposed.

- [ ] **Step 8: Commit the Gnani STT boundary**

```bash
git add apps/core/gnani_client.py apps/api/routers/voice.py backend/main.py apps/api/security.py tests/unit/test_gnani_client.py backend/tests/test_voice_audio.py backend/tests/test_voice_security.py backend/tests/test_role_access.py
git commit -m "feat: add Gnani speech transcription"
```

### Task 3: Connect multilingual question handling and the frontend microphone flow

**Files:**
- Modify: `apps/api/routers/query.py`
- Modify: `backend/tests/test_query_approval.py`
- Modify: `frontend/src/pages/AskData.jsx`
- Modify: `frontend/src/pages/__tests__/role-surfaces.test.jsx` if endpoint behavior is covered there

**Interfaces:**
- Consumes `GroqSQLClient.translate_to_english(question, language_code)` from Task 1 and `POST /api/voice/transcribe` from Task 2.
- Produces unchanged generate-query and voice transcript response payloads.

- [ ] **Step 1: Write failing query-language tests**

Add one test proving an English question does not call translation and one proving a Hindi/Tamil-script question calls `translate_to_english` exactly once before planning. Assert that translation failures produce the existing safe query-generation error and do not reach SQL generation.

- [ ] **Step 2: Run query-language tests to verify they fail**

Run: `pytest backend/tests/test_query_approval.py -k "translation or language" -q`

Expected: FAIL because query routing still imports and calls `SarvamClient` for translation and localizes outputs.

- [ ] **Step 3: Replace Sarvam query language calls with Groq input translation**

In `apps/api/routers/query.py`, remove Sarvam imports and `_translation_cache`. Keep script/language detection. Call the Groq translator only from `_translate_for_sql` for a detected non-English language. Make display translation and row localization pass-through functions for this temporary English-output mode so result rendering stays stable without extra model calls.

- [ ] **Step 4: Update the microphone endpoint in `AskData.jsx`**

Change only the fetch target from `/sarvam/transcribe` to `/voice/transcribe`. Preserve `FormData`, Safari-compatible filename selection, transcript append behavior, and the returned `language_code` handling.

- [ ] **Step 5: Run query and frontend behavior tests to verify they pass**

Run: `pytest backend/tests/test_query_approval.py -q && npm --prefix frontend test -- --run`

Expected: PASS, including English bypass, one non-English translation call, and unchanged voice submission UX.

- [ ] **Step 6: Commit multilingual input integration**

```bash
git add apps/api/routers/query.py backend/tests/test_query_approval.py frontend/src/pages/AskData.jsx frontend/src/pages/__tests__/role-surfaces.test.jsx
git commit -m "feat: translate non-English questions with Groq"
```

### Task 4: Remove retired provider surfaces and update configuration/copy

**Files:**
- Delete: `apps/core/sarvam_client.py`
- Delete: `apps/api/routers/sarvam.py`
- Delete: `tests/unit/test_sarvam_client.py`
- Delete: `backend/tests/test_sarvam_security.py`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `frontend/src/components/landing/Sections.jsx`
- Modify: `backend/tests/test_role_access.py`

**Interfaces:**
- Consumes completed Groq/Gnani boundaries from Tasks 1–3.
- Produces provider documentation and configuration containing only Groq and Gnani references.

- [ ] **Step 1: Write failing static configuration and landing-copy tests**

Add/extend a frontend semantic test and a lightweight backend test that assert `.env.example`, requirements, and the landing provider list contain `GNANI_API_KEY` and `GROQ_API_KEY`, and contain no case-insensitive `anthropic`, `claude`, `sarvam`, or `LOCAL_SQL_` provider configuration.

- [ ] **Step 2: Run the cleanup tests to verify they fail**

Run: `pytest backend/tests/test_provider_cleanup.py -q && npm --prefix frontend test -- --run src/__tests__/visual-semantics.test.jsx`

Expected: FAIL because retired provider dependencies, settings, and copy still exist.

- [ ] **Step 3: Delete retired code and replace dependencies/configuration**

Remove the Sarvam files/tests and references. Remove `anthropic` and `sarvamai` from requirements. Replace the provider section of `.env.example` with only the Groq and Gnani values specified in the migration spec. Rewrite README and landing copy to describe Groq-backed read-only SQL and Gnani voice transcription without claiming output translation.

- [ ] **Step 4: Update role tests and provider-cleanup tests**

Replace the old protected Sarvam translation assertion with `/api/voice/transcribe` authorization. Add `backend/tests/test_provider_cleanup.py` to scan the explicit provider/configuration files—not the historical migration spec—for retired provider references.

- [ ] **Step 5: Run cleanup tests to verify they pass**

Run: `pytest backend/tests/test_provider_cleanup.py backend/tests/test_role_access.py -q && npm --prefix frontend test -- --run src/__tests__/visual-semantics.test.jsx`

Expected: PASS; the codebase has no active retired-provider surface.

- [ ] **Step 6: Commit provider cleanup and docs**

```bash
git add -A apps/core apps/api requirements.txt .env.example README.md frontend/src/components/landing backend/tests tests/unit
git commit -m "chore: remove retired AI providers"
```

### Task 5: Run integration verification and inspect the migration boundary

**Files:**
- Modify only if verification exposes a regression.

**Interfaces:**
- Consumes all completed migration tasks.
- Produces verified Groq-only query behavior and Gnani-only STT behavior without credentials committed to the worktree.

- [ ] **Step 1: Run the complete backend suite**

Run: `pytest -q`

Expected: PASS with all provider/network calls mocked at their boundary.

- [ ] **Step 2: Run frontend verification**

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run lint && npm --prefix frontend run build`

Expected: all commands exit 0.

- [ ] **Step 3: Search the active runtime surfaces for retired providers**

Run: `rg -n -i "anthropic|claude|sarvam|LOCAL_SQL|mlx" apps backend frontend/src requirements.txt .env.example README.md`

Expected: no matches outside explicitly retained migration-history documentation, if any.

- [ ] **Step 4: Inspect the final diff and commit verification fixes if needed**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intended migration files are staged for the final commit.

## Plan self-review

- Spec coverage: Tasks 1–4 map respectively to Groq-only behavior, Gnani STT, multilingual input, and retirement/configuration; Task 5 verifies the complete result.
- Step scan: every implementation task begins with a failing test and ends with a targeted green check before its commit.
- Type consistency: Task 1 defines the Groq interfaces consumed by Task 3; Task 2 defines the voice route consumed by Task 3; no Sarvam/Claude/local interface is consumed after its deletion.
- Review focus: all five listed failure modes have a named test in their owning task.
- Proportion: implementation details are limited to interfaces, exact values, and safety constraints; no production code is embedded.
