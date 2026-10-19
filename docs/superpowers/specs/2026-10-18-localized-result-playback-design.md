# Localized result playback design

## Goal

Let an authorized user listen to the concise, verified answer in the language
they selected for their question. Playback is always initiated by the user and
does not read raw table rows aloud.

## Scope

- Add authenticated Gnani Timbre v3 synthesis behind the existing `/api/voice`
  router.
- Request a WAV response for browser playback.
- Add a result-summary control with play, pause/resume, stop, loading, and
  failure states.
- Visually emphasize the executive summary and cycle the existing key-value
  highlight chips during active playback.

## Data flow and boundaries

1. The client sends the rendered executive headline and optional detail, plus
   the existing selected BCP-47 language code, to `/api/voice/synthesize`.
2. The backend validates the authenticated caller, supported language, and a
   short text limit before calling Gnani. It keeps the API key server-side.
3. Gnani Timbre v3 returns a mono WAV clip. The backend forwards it as binary
   audio with no persistent storage or logging of the answer text.
4. The client uses an object URL and a single `Audio` instance to play the
   clip. URLs are revoked when playback ends, is stopped, an error occurs, or a
   different result replaces the report.

Only the user-visible executive answer is submitted to TTS. SQL, detailed
result rows, connection information, and hidden metadata are excluded.

### Data sent to outside services

- **Gnani TTS:** the visible answer headline and detail text (at most 2,000
  characters) and the selected language code, only when the user presses
  "Listen to answer".
- **Gnani STT:** the voice recording and the selected language code, only when
  the user records a voice question.
- The main LLM (planned: DeepSeek, not Groq) and the translation provider are
  covered in the provider-migration spec.

## UI behavior

- The result summary shows `Listen to answer` at rest.
- While synthesis is pending it shows a disabled `Preparing audio…` state.
- While playing it exposes `Pause` and `Stop`; pausing changes the primary
  action to `Resume`.
- The summary receives an `is-speaking` class and highlight chips receive a
  staggered pulse. There is no simulated word-level synchronization because
  the REST response has no timing metadata.
- Reduced-motion users get the same state indication without the pulse.
- A compact inline error explains an unavailable speech service without
  hiding the report.

## Provider contract

Use `POST https://api.vachana.ai/api/v1/tts/inference` with the existing
server-side Gnani key. The request uses Timbre v3, one multilingual voice,
the selected language, and WAV/linear PCM output. The current Gnani REST
documentation lists the endpoint, `X-API-Key-ID` authentication, multilingual
Timbre v3 support, and WAV output.

## Error handling

- Invalid client text/language: `400`.
- Missing provider configuration: `503`.
- Gnani authorization, rate, or availability failures: safe `502` response;
  no provider response body or credential reaches the client.
- Browser playback errors clean up the object URL and restore the idle state.

## Verification

- Unit-test Gnani TTS request shape and binary response handling.
- Router test proves a selected language reaches the provider and that only
  the requested summary text is synthesized.
- Frontend test covers export of the playback control and state classes.
- Run the full backend and frontend suites, lint, production build, and
  whitespace check.
