"""Voice transcription sends the correct in-memory file to OpenAI."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from transcription import TranscriptionUnavailable, transcribe_audio
from whatsapp import DownloadedMedia


def ogg_opus(duration_seconds: float, *, pre_skip: int = 312) -> bytes:
    """Build the small amount of Ogg structure the duration reader needs."""
    opus_head = b"OpusHead" + bytes([1, 1]) + pre_skip.to_bytes(2, "little") + b"\x00" * 7

    def page(body: bytes, granule: int, sequence: int) -> bytes:
        return (
            b"OggS"
            + bytes([0, 0])
            + granule.to_bytes(8, "little")
            + (1).to_bytes(4, "little")
            + sequence.to_bytes(4, "little")
            + b"\x00" * 4
            + bytes([1, len(body)])
            + body
        )

    final_granule = pre_skip + round(duration_seconds * 48_000)
    return page(opus_head, 0, 0) + page(b"\x00", final_granule, 1)


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
    audio = ogg_opus(30)
    media = DownloadedMedia(audio, "audio/ogg", "whatsapp-123.ogg")

    result = await transcribe_audio(media, client=client, model="test-transcriber")

    assert result == "mama noodles dekak gannawa"
    call = transcriptions.calls[0]
    assert call["model"] == "test-transcriber"
    assert call["file"] == ("whatsapp-123.ogg", audio, "audio/ogg")
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


async def test_rejects_voice_note_over_two_minutes_before_provider_call():
    transcriptions = FakeTranscriptions("must not be called")
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))

    with pytest.raises(TranscriptionUnavailable, match="maximum is 120 seconds"):
        await transcribe_audio(
            DownloadedMedia(ogg_opus(120.1), "audio/ogg", "long.ogg"),
            client=client,
        )

    assert transcriptions.calls == []


async def test_rejects_unknown_duration_before_provider_call():
    transcriptions = FakeTranscriptions("must not be called")
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))

    with pytest.raises(TranscriptionUnavailable, match="cannot safely determine"):
        await transcribe_audio(
            DownloadedMedia(b"mp3 bytes", "audio/mpeg", "unknown.mp3"),
            client=client,
        )

    assert transcriptions.calls == []
