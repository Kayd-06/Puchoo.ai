"""Sarvam language adapter router."""

from typing import Dict
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from apps.core.sarvam_client import SarvamClient, SarvamConfigurationError

router = APIRouter(prefix="/sarvam", tags=["sarvam"])

class TranslationRequest(BaseModel):
    text: str
    target_language: str
    source_language: str = "en-IN"

@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> Dict[str, str]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty audio file provided.")
    try:
        client = SarvamClient()
        transcript = client.transcribe(contents, filename=file.filename or "audio.wav")
        return {"transcript": transcript}
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
