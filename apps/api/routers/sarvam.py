"""Sarvam language adapter router."""

import logging
import re
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.core.sarvam_client import SarvamClient, SarvamConfigurationError
from apps.api.security import require_data_manager
from backend.config import settings

router = APIRouter(prefix="/sarvam", tags=["sarvam"])
logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = settings.upload_max_bytes
_AUDIO_SIGNATURES = {
    ".webm": (b"\x1a\x45\xdf\xa3",),
    ".wav": (b"RIFF",),
    ".ogg": (b"OggS",),
    ".mp3": (b"ID3",),
}

class TranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=2_000, strict=True)
    target_language: str = Field(min_length=5, max_length=5, strict=True)
    source_language: str = Field(default="en-IN", min_length=5, max_length=5, strict=True)

    @field_validator("target_language", "source_language")
    @classmethod
    def valid_language_code(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", value):
            raise ValueError("Use a BCP-47 language code such as hi-IN.")
        return value


async def _read_audio(file: UploadFile) -> bytes:
    contents = await file.read(MAX_AUDIO_BYTES + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="Empty audio file provided.")
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="The audio file is too large.")
    suffix = Path(file.filename or "").suffix.lower()
    signatures = _AUDIO_SIGNATURES.get(suffix)
    if signatures is None or not any(contents.startswith(signature) for signature in signatures):
        # MP3 frame-sync is valid when no ID3 metadata is present.
        if not (suffix == ".mp3" and len(contents) >= 2 and contents[0] == 0xFF and contents[1] & 0xE0 == 0xE0):
            raise HTTPException(status_code=400, detail="The audio file content does not match its declared format.")
    if suffix == ".wav" and contents[8:12] != b"WAVE":
        raise HTTPException(status_code=400, detail="The audio file content does not match its declared format.")
    return contents

@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), user=Depends(require_data_manager)) -> Dict[str, str | None]:
    contents = await _read_audio(file)
    try:
        client = SarvamClient()
        # Keep the transcript in the language spoken. Sarvam auto-detects its
        # supported languages when no language is specified.
        transcription = client.transcribe_with_metadata(
            contents,
            filename=file.filename or "audio.webm",
            translate_to_english=False,
        )
        return {"transcript": transcription.transcript, "language_code": transcription.language_code}
    except SarvamConfigurationError:
        raise HTTPException(status_code=503, detail="Speech transcription is not configured.") from None
    except Exception as exc:
        logger.exception("Sarvam transcription failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Transcription is temporarily unavailable.") from None

@router.post("/translate")
def translate(request: TranslationRequest, user=Depends(require_data_manager)) -> Dict[str, str]:
    try:
        client = SarvamClient()
        translated = client.translate(
            request.text, 
            request.target_language, 
            source_language=request.source_language
        )
        return {"translated_text": translated}
    except SarvamConfigurationError:
        raise HTTPException(status_code=503, detail="Translation is not configured.") from None
    except Exception as exc:
        logger.exception("Sarvam translation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Translation is temporarily unavailable.") from None
