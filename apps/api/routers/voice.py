"""Authenticated speech-to-text upload endpoint."""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from apps.api.security import require_capability
from apps.core.gnani_client import DEFAULT_LANGUAGE_CODE, SUPPORTED_LANGUAGE_CODES, GnaniClient, GnaniConfigurationError
from backend.config import settings

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = settings.upload_max_bytes
_AUDIO_SIGNATURES = {".webm": (b"\x1a\x45\xdf\xa3",), ".wav": (b"RIFF",), ".ogg": (b"OggS",), ".mp3": (b"ID3",)}


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


async def _read_audio(file: UploadFile) -> bytes:
    contents = await file.read(MAX_AUDIO_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="Empty audio file provided.")
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="The audio file is too large.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in {".mp4", ".m4a"}:
        valid = len(contents) >= 8 and contents[4:8] == b"ftyp"
    else:
        signatures = _AUDIO_SIGNATURES.get(suffix)
        valid = signatures is not None and any(contents.startswith(signature) for signature in signatures)
        valid = valid or (suffix == ".mp3" and len(contents) >= 2 and contents[0] == 0xFF and contents[1] & 0xE0 == 0xE0)
    if not valid or (suffix == ".wav" and contents[8:12] != b"WAVE"):
        raise HTTPException(status_code=400, detail="The audio file content does not match its declared format.")
    return contents


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language_code: str = Form(DEFAULT_LANGUAGE_CODE),
    user=Depends(require_capability("query_workspace")),
) -> dict[str, str | None]:
    contents = await _read_audio(file)
    selected_language = language_code.strip()
    if selected_language not in SUPPORTED_LANGUAGE_CODES:
        raise HTTPException(status_code=400, detail="Choose a supported speech language.")
    try:
        result = GnaniClient().transcribe(contents, file.filename or "audio.webm", language_code=selected_language)
        return {"transcript": result.transcript, "language_code": result.language_code or selected_language}
    except GnaniConfigurationError as exc:
        if "not configured" in str(exc):
            raise HTTPException(status_code=503, detail="Speech transcription is not configured.") from None
        logger.warning("Gnani transcription unavailable")
        raise HTTPException(status_code=502, detail="Transcription is temporarily unavailable.") from None
    except Exception:
        logger.exception("Gnani transcription failed")
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
        logger.warning("Gnani speech synthesis unavailable")
        raise HTTPException(status_code=502, detail="Speech synthesis is temporarily unavailable.") from None
    except Exception:
        logger.warning("Gnani speech synthesis failed")
        raise HTTPException(status_code=502, detail="Speech synthesis is temporarily unavailable.") from None
