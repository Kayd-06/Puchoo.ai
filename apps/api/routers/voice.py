"""Authenticated speech-to-text upload endpoint."""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from apps.api.security import require_capability
from apps.core.gnani_client import SUPPORTED_LANGUAGE_CODES, GnaniClient, GnaniConfigurationError
from backend.config import settings

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = settings.upload_max_bytes
# Only formats the browser actually sends and Gnani accepts. Chromium's WebM
# recordings are converted to WAV in the browser before upload.
_AUDIO_SIGNATURES = {".wav": (b"RIFF",), ".ogg": (b"OggS",)}
_ISO_BMFF_SUFFIXES = {".mp4", ".m4a"}
ALLOWED_AUDIO_SUFFIXES = frozenset(_AUDIO_SIGNATURES) | _ISO_BMFF_SUFFIXES


class SynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=2_000, strict=True)
    language_code: str = Field(min_length=5, max_length=5, strict=True)

    @field_validator("language_code")
    @classmethod
    def supported_language(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGE_CODES:
            raise ValueError("Choose a supported speech language.")
        return value


async def _read_audio(file: UploadFile) -> tuple[bytes, str]:
    """Return the bounded upload and its validated, lower-case suffix."""
    contents = await file.read(MAX_AUDIO_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="Empty audio file provided.")
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="The audio file is too large.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_AUDIO_SUFFIXES:
        raise HTTPException(status_code=400, detail="Record in OGG, M4A, MP4, or WAV format.")
    if suffix in _ISO_BMFF_SUFFIXES:
        valid = len(contents) >= 8 and contents[4:8] == b"ftyp"
    else:
        valid = any(contents.startswith(signature) for signature in _AUDIO_SIGNATURES[suffix])
    if not valid or (suffix == ".wav" and contents[8:12] != b"WAVE"):
        raise HTTPException(status_code=400, detail="The audio file content does not match its declared format.")
    return contents, suffix


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language_code: str | None = Form(None),
    user=Depends(require_capability("query_workspace")),
) -> dict[str, str | None]:
    contents, suffix = await _read_audio(file)
    selected_language = language_code.strip() if isinstance(language_code, str) and language_code.strip() else None
    if selected_language is not None and selected_language not in SUPPORTED_LANGUAGE_CODES:
        raise HTTPException(status_code=400, detail="Choose a supported speech language.")
    try:
        # The browser-supplied name never reaches Gnani; the suffix was validated above.
        result = await run_in_threadpool(
            GnaniClient().transcribe,
            contents,
            f"audio{suffix}",
            language_code=selected_language,
        )
        return {"transcript": result.transcript, "language_code": result.language_code or selected_language}
    except GnaniConfigurationError as exc:
        if "not configured" in str(exc):
            raise HTTPException(status_code=503, detail="Speech transcription is not configured.") from None
        logger.warning("Gnani transcription unavailable: %s", type(exc.__cause__ or exc).__name__)
        raise HTTPException(status_code=502, detail="Transcription is temporarily unavailable.") from None
    except Exception as exc:
        logger.warning("Gnani transcription failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Transcription is temporarily unavailable.") from None


@router.post("/synthesize")
async def synthesize(
    payload: dict[str, Any] = Body(...),
    user=Depends(require_capability("query_workspace")),
) -> Response:
    try:
        request = SynthesisRequest.model_validate(payload)
    except ValidationError as exc:
        language_errors = [error for error in exc.errors() if error.get("loc") == ("language_code",)]
        if language_errors:
            raise HTTPException(status_code=400, detail="Choose a supported speech language.") from None
        raise HTTPException(status_code=400, detail="Provide a short answer to read aloud.") from None

    try:
        audio = await run_in_threadpool(
            GnaniClient().synthesize,
            request.text,
            language_code=request.language_code,
        )
        return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
    except GnaniConfigurationError as exc:
        if "not configured" in str(exc):
            raise HTTPException(status_code=503, detail="Speech synthesis is not configured.") from None
        logger.warning("Gnani speech synthesis unavailable: %s", type(exc.__cause__ or exc).__name__)
        raise HTTPException(status_code=502, detail="Speech synthesis is temporarily unavailable.") from None
    except Exception as exc:
        logger.warning("Gnani speech synthesis failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Speech synthesis is temporarily unavailable.") from None
