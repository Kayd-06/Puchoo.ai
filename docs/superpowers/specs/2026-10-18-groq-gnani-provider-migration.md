# Groq and Gnani provider migration

> **Status update (2026-10-19):** Groq is no longer the planned language model.
> The team plans to use **DeepSeek** (OpenAI-compatible API) instead; read
> "Groq" below as "the main LLM". Gnani's public API offers speech-to-text,
> text-to-speech and voice cloning only — it has **no text-to-text translation
> endpoint** — so question/answer translation cannot move to Gnani. Until the
> main LLM takes over translation, `apps/api/routers/query.py` still calls
> Sarvam for it. Gnani STT also has no `auto` language: the browser sends the
> language chosen in the voice picker, with `GNANI_STT_LANGUAGE` (default
> `en-IN`) as the server fallback.

## Goal

Temporarily run Puchoo.si with Groq as the sole language-model provider and
Gnani Prisma as the sole speech-to-text provider. Remove every Claude,
Anthropic, local-MLX, and Sarvam dependency, setting, route, test, and user
facing reference. API credentials remain in an untracked local `.env` file.

## User-facing behaviour

- Text and voice questions may be in Indian English, Hindi, Tamil, Telugu,
  Bengali, Marathi, Gujarati, Kannada, Malayalam, or Punjabi. The user picks
  the spoken language in a voice-language picker and that BCP-47 code is sent
  to Gnani (its REST STT API requires an explicit language code).
- The microphone interaction and its browser fallback remain unchanged. The
  frontend sends recordings to `POST /api/voice/transcribe`, which preserves
  the existing `{ transcript, language_code }` response shape.
- English questions proceed directly to Groq SQL planning. A non-English
  question is translated to English once, before the existing SQL planner,
  generator, guardrail, approval, and execution pipeline runs.
- Executive summaries, table labels, and returned string cells remain English
  in this temporary configuration. This avoids multiple Groq calls per query
  and protects the available credits while retaining multilingual input.

## Provider boundaries

### Groq

- `GroqSQLClient` becomes the only SQL, repair, and verification client.
- Add one narrowly scoped translation method that accepts at most the existing
  question limit and has its own low output-token cap. It must preserve
  numbers, dates, names, table-like identifiers, and quoted values exactly.
- `PUCHOO_SQL_PROVIDER` is no longer a provider selector. Groq is mandatory;
  startup/query failures without `GROQ_API_KEY` produce the existing safe
  configuration error rather than falling back to an external provider.
- Keep SQL parsing, read-only execution, query approval, and schema reduction
  unchanged. Translation output is still untrusted model text and is never
  executable.

### Gnani

- Add a small `GnaniClient` that makes a server-side multipart request to
  Gnani STT. It reads `GNANI_API_KEY` only from the process environment and
  sends it as `X-API-Key-ID`.
- Never forward the browser's filename; send a fixed `audio.<ext>` name after
  the existing size/signature validation (WAV, OGG, M4A/MP4 only). The adapter returns a non-empty transcript plus a normalized
  BCP-47 language code when Gnani supplies one.
- Add the `/api/voice/transcribe` router. It retains the current query-role
  authorization, response schema, bounded upload read, generic external-error
  response, and non-sensitive server logs.
- Do not add streaming STT, TTS, or a client-side provider key in this change.

## Retired surfaces

- Delete `apps/core/sarvam_client.py` and the Sarvam router, translation
  endpoint, tests, route exception, and frontend endpoint reference.
- Delete Anthropic/Claude and local-MLX clients, configuration error classes,
  factory branches, compatibility aliases, unit tests, package dependencies,
  environment variables, documentation, and landing-page provider copy.
- Replace Sarvam tests with Gnani boundary tests. Remove Claude/local-model
  tests rather than leaving compatibility shims.

## Configuration

The new `.env.example` provider section contains only:

```dotenv
GROQ_API_KEY=
GROQ_MODEL=
GROQ_PLANNER_MODEL=
GROQ_VERIFIER_MODEL=
GROQ_TRANSLATION_MODEL=
GROQ_BASE_URL=https://api.groq.com/openai/v1/chat/completions
GROQ_MAX_TOKENS=1800
GROQ_TRANSLATION_MAX_TOKENS=320
GNANI_API_KEY=
GNANI_STT_LANGUAGE=en-IN
```

`GROQ_TRANSLATION_MODEL` falls back to `GROQ_MODEL`; it does not create a
second mandatory credential. The Groq endpoint, model, and token values remain
configurable, because provider availability can vary by Groq account. All
non-provider application settings in `.env.example` remain unchanged.

## Data sent to outside services

| Data | Sent to | When |
| --- | --- | --- |
| Voice recording (audio) | Gnani STT (`api.vachana.ai/stt/v3`) | User records a voice question |
| Visible answer headline + detail (text, ≤2,000 chars) | Gnani TTS (`api.vachana.ai/api/v1/tts/inference`) | User presses "Listen to answer" |
| Non-English question text; answer text, labels and text cells for translation | Sarvam (until the main LLM takes over) | Question language is not English |
| Question, schema summary, sample values | Main LLM (planned: DeepSeek) | Every query |

SQL, raw result rows (except text cells translated for display), connection
details and credentials are never sent to Gnani. Nothing is stored by Puchoo
beyond the existing query history.

## Error handling

- Missing `GNANI_API_KEY` returns a clear 503 only from the voice endpoint.
- Missing `GROQ_API_KEY` returns the existing safe query-configuration error;
  no local or Claude fallback is attempted.
- Gnani transport, authentication, unsupported-audio, or malformed-response
  failures become a generic 502 without leaking keys or upstream response
  bodies.
- Groq translation failure blocks only that non-English query with a clear
  retry message. It does not produce SQL from untranslated text.

## Test plan

- Unit-test Groq-only client construction, translation request bounds, and
  translation failure handling with fake HTTP responses.
- Unit-test Gnani request headers, multipart field names, transcript parsing,
  missing configuration, malformed payloads, and non-leaking errors.
- Update route/security tests for `/api/voice/transcribe`; retain audio-size
  and signature coverage.
- Update query tests to cover English bypass and one non-English translation
  path, while keeping guardrail and approval tests intact.
- Run backend tests, frontend tests, lint, production build, and diff checks.

## Out of scope

- No production API key is added or logged.
- No automatic credit accounting is invented without Gnani/Groq billing API
  contracts.
- No TTS, real-time STT, DeepSeek, Sarvam, or Claude fallback is retained.
