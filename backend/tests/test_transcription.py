"""Voice transcription sends the correct in-memory file to OpenAI."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from transcription import TranscriptionUnavailable, transcribe_audio
from whatsapp import DownloadedMedia


class FakeTranscriptions:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


async def test_transcribes_in_memory_audio_with_configured_model():
    transcriptions = FakeTranscriptions("  mama noodles dekak gannawa  ")
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))
    media = DownloadedMedia(b"audio", "audio/ogg", "whatsapp-123.ogg")

    result = await transcribe_audio(media, client=client, model="test-transcriber")

    assert result == "mama noodles dekak gannawa"
    call = transcriptions.calls[0]
    assert call["model"] == "test-transcriber"
    assert call["file"] == ("whatsapp-123.ogg", b"audio", "audio/ogg")
    assert call["response_format"] == "json"


async def test_rejects_non_audio_before_calling_provider():
    client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=FakeTranscriptions("unused"))
    )

    with pytest.raises(TranscriptionUnavailable, match="MIME type"):
        await transcribe_audio(
            DownloadedMedia(b"image", "image/jpeg", "receipt.jpg"), client=client
        )

    assert client.audio.transcriptions.calls == []
