"""Turn a WhatsApp voice note into text before the sales agent sees it.

Audio bytes live only for this call. They are not written to disk or logged;
the transcript is persisted on the message row so staff and later agent turns
can read what the customer said.
"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from config import settings
from whatsapp import DownloadedMedia


class TranscriptionUnavailable(RuntimeError):
    """The feature is not configured or the received file cannot be used."""


async def transcribe_audio(
    media: DownloadedMedia,
    *,
    client: Any | None = None,
    model: str | None = None,
) -> str:
    """Transcribe one voice note, preserving its spoken language."""
    if not media.content:
        raise TranscriptionUnavailable("voice note was empty")
    if len(media.content) > settings.voice_max_bytes:
        raise TranscriptionUnavailable("voice note exceeded the configured size limit")
    if not media.mime_type.startswith("audio/"):
        raise TranscriptionUnavailable(f"unsupported voice-note MIME type: {media.mime_type}")

    owned_client = client is None
    if client is None:
        api_key = settings.openai_api_key.get_secret_value()
        if not api_key:
            raise TranscriptionUnavailable("OPENAI_API_KEY is not configured")
        client = AsyncOpenAI(
            api_key=api_key,
            timeout=settings.voice_transcription_timeout_seconds,
            max_retries=2,
        )

    try:
        result = await client.audio.transcriptions.create(
            model=model or settings.voice_transcription_model,
            file=(media.filename, media.content, media.mime_type),
            response_format="json",
        )
        text = str(getattr(result, "text", "") or "").strip()
        if not text:
            raise TranscriptionUnavailable("transcription returned no text")
        return text
    finally:
        if owned_client:
            await client.close()
