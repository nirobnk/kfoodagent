"""Turn a WhatsApp voice note into text before the sales agent sees it.

Audio bytes live only for this call. They are not written to disk or logged;
the transcript is persisted on the message row so staff and later agent turns
can read what the customer said.
"""

from __future__ import annotations

import io
import wave
from typing import Any

from openai import AsyncOpenAI

from config import settings
from whatsapp import DownloadedMedia


class TranscriptionUnavailable(RuntimeError):
    """The feature is not configured or the received file cannot be used."""


def audio_duration_seconds(media: DownloadedMedia) -> float:
    """Read duration locally; reject formats whose length cannot be trusted.

    WhatsApp voice notes arrive as Ogg/Opus. WAV is included for ordinary
    audio attachments and tests. Unknown containers are intentionally refused:
    sending one to the paid API would make the duration limit advisory rather
    than hard.
    """
    mime_type = media.mime_type.split(";", 1)[0].strip().lower()
    if mime_type in {"audio/ogg", "application/ogg"}:
        return _ogg_opus_duration(media.content)
    if mime_type in {"audio/wav", "audio/wave", "audio/x-wav"}:
        return _wav_duration(media.content)
    raise TranscriptionUnavailable(
        f"cannot safely determine voice-note duration for {mime_type or 'unknown format'}"
    )


def _ogg_opus_duration(content: bytes) -> float:
    """Calculate Ogg/Opus duration from page granules without decoding audio."""
    position = 0
    pre_skip: int | None = None
    final_granule: int | None = None

    while position < len(content):
        if position + 27 > len(content) or content[position : position + 4] != b"OggS":
            raise TranscriptionUnavailable("voice note has an invalid Ogg container")

        segment_count = content[position + 26]
        header_end = position + 27 + segment_count
        if header_end > len(content):
            raise TranscriptionUnavailable("voice note has a truncated Ogg header")

        body_size = sum(content[position + 27 : header_end])
        page_end = header_end + body_size
        if page_end > len(content):
            raise TranscriptionUnavailable("voice note has a truncated Ogg page")

        page_body = content[header_end:page_end]
        if pre_skip is None:
            opus_head = page_body.find(b"OpusHead")
            if opus_head >= 0 and opus_head + 12 <= len(page_body):
                pre_skip = int.from_bytes(
                    page_body[opus_head + 10 : opus_head + 12], "little"
                )

        granule = int.from_bytes(content[position + 6 : position + 14], "little")
        if granule != 0xFFFFFFFFFFFFFFFF:
            final_granule = max(final_granule or 0, granule)
        position = page_end

    if pre_skip is None or final_granule is None or final_granule <= pre_skip:
        raise TranscriptionUnavailable("voice note does not contain valid Opus timing data")
    # Opus granule positions are always measured at 48 kHz, regardless of the
    # original input sample rate recorded in OpusHead.
    return (final_granule - pre_skip) / 48_000


def _wav_duration(content: bytes) -> float:
    try:
        with wave.open(io.BytesIO(content), "rb") as audio:
            frame_rate = audio.getframerate()
            if frame_rate <= 0:
                raise TranscriptionUnavailable("voice note has an invalid WAV sample rate")
            return audio.getnframes() / frame_rate
    except (EOFError, wave.Error) as exc:
        raise TranscriptionUnavailable("voice note has an invalid WAV container") from exc


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

    duration = audio_duration_seconds(media)
    if duration > settings.voice_max_duration_seconds:
        raise TranscriptionUnavailable(
            f"voice note is {duration:.1f} seconds; maximum is "
            f"{settings.voice_max_duration_seconds:.0f} seconds"
        )

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
