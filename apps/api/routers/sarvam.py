"""Sarvam text-translation router.

Sarvam is used only for translation. Speech-to-text and text-to-speech go
through Gnani (see apps/api/routers/voice.py).
"""

import logging
import re
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.core.sarvam_client import SarvamClient, SarvamConfigurationError
from apps.api.security import require_capability

router = APIRouter(prefix="/sarvam", tags=["sarvam"])
logger = logging.getLogger(__name__)


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


@router.post("/translate")
def translate(request: TranslationRequest, user=Depends(require_capability("query_workspace"))) -> Dict[str, str]:
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
