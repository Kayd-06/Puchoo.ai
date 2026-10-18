"""Authenticated speech-to-text upload endpoint."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from apps.api.security import require_capability
from apps.core.gnani_client import GnaniClient, GnaniConfigurationError
from backend.config import settings

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = settings.upload_max_bytes
_AUDIO_SIGNATURES = {".webm": (b"\x1a\x45\xdf\xa3",), ".wav": (b"RIFF",), ".ogg": (b"OggS",), ".mp3": (b"ID3",)}


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
async def transcribe(file: UploadFile = File(...), user=Depends(require_capability("query_workspace"))) -> dict[str, str | None]:
    contents = await _read_audio(file)
    try:
        result = GnaniClient().transcribe(contents, file.filename or "audio.webm")
        return {"transcript": result.transcript, "language_code": result.language_code}
    except GnaniConfigurationError as exc:
        if "not configured" in str(exc):
            raise HTTPException(status_code=503, detail="Speech transcription is not configured.") from None
        logger.warning("Gnani transcription unavailable")
        raise HTTPException(status_code=502, detail="Transcription is temporarily unavailable.") from None
    except Exception:
        logger.exception("Gnani transcription failed")
        raise HTTPException(status_code=502, detail="Transcription is temporarily unavailable.") from None
