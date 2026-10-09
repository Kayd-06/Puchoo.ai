"""Tests for audio file parsing and validation."""

import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from apps.api.routers.sarvam import _read_audio

def test_mp4_m4a_audio_uploads():
    """ISO-BMFF audio files from Safari are accepted using their ftyp signature."""
    async def check() -> None:
        # Valid MP4 has the ISO-BMFF `ftyp` marker at byte four.
        content = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"
        file = UploadFile(filename="voice.m4a", file=BytesIO(content))
        assert await _read_audio(file) == content

        file = UploadFile(filename="voice.mp4", file=BytesIO(content))
        assert await _read_audio(file) == content

        invalid_content = b"RIFF\x00\x00\x00\x00WAVE"
        file = UploadFile(filename="voice.m4a", file=BytesIO(invalid_content))
        with pytest.raises(HTTPException) as exc:
            await _read_audio(file)
        assert exc.value.status_code == 400
        assert "does not match its declared format" in exc.value.detail

    asyncio.run(check())
