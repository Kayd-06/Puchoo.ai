"""Sarvam language adapter router."""

from typing import Dict
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from apps.core.sarvam_client import SarvamClient, SarvamConfigurationError

router = APIRouter(prefix="/sarvam", tags=["sarvam"])

class TranslationRequest(BaseModel):
    text: str
    target_language: str
    source_language: str = "en-IN"

@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> Dict[str, str | None]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty audio file provided.")
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
    except SarvamConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")

@router.post("/translate")
def translate(request: TranslationRequest) -> Dict[str, str]:
    try:
        client = SarvamClient()
        translated = client.translate(
            request.text, 
            request.target_language, 
            source_language=request.source_language
        )
        return {"translated_text": translated}
    except SarvamConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Translation failed: {exc}")
