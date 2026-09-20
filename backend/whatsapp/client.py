"""The only place in this codebase that talks to Meta's Graph API.

Nothing else may POST to graph.facebook.com — see plan.md §8. Every send is
logged with the recipient, whether it was text or a template, and the result.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DownloadedMedia:
    """A WhatsApp attachment held in memory only for immediate processing."""

    content: bytes
    mime_type: str
    filename: str


_MEDIA_EXTENSIONS = {
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "audio/m4a": ".m4a",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}

# Meta error codes that will never succeed on retry.
PERMANENT_CODES = {
    100,  # invalid parameter
    131_026,  # message undeliverable / not a WhatsApp user
    131_047,  # re-engagement required (outside the 24h window)
    131_051,  # unsupported message type
    132_000,  # template param count mismatch
    132_001,  # template does not exist
    132_005,  # template hydrated text too long
    133_010,  # number not registered
    190,  # access token expired or invalid
}


class WhatsAppError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, status: int | None = None,
                 details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details

    @property
    def is_permanent(self) -> bool:
        return self.code in PERMANENT_CODES or (self.status is not None and 400 <= self.status < 500
                                                and self.status != 429)


class _Retryable(RuntimeError):
    """Internal marker so tenacity retries transient failures only."""


class WhatsAppClient:
    def __init__(
        self,
        *,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        api_base: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._token = access_token or settings.wa_access_token.get_secret_value()
        self._phone_number_id = phone_number_id or settings.wa_phone_number_id
        self._base = (api_base or settings.graph_api_base).rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )

    # -- lifecycle ---------------------------------------------------------
    async def aclose(self) -> None:
        await self._client.aclose()

    # -- low level ---------------------------------------------------------
    @retry(
        retry=retry_if_exception_type(_Retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/{path.lstrip('/')}"
        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise _Retryable(str(exc)) from exc

        if response.status_code >= 500 or response.status_code == 429:
            raise _Retryable(f"{response.status_code}: {response.text[:200]}")

        if response.status_code >= 400:
            body = _safe_json(response)
            error = (body.get("error") or {}) if isinstance(body, dict) else {}
            raise WhatsAppError(
                error.get("message") or f"HTTP {response.status_code}",
                code=error.get("code"),
                status=response.status_code,
                details=error,
            )

        return _safe_json(response)

    # -- sending -----------------------------------------------------------
    async def send_text(self, wa_id: str, body: str, *, preview_url: bool = False) -> str:
        """Send free-form text. Only legal inside the 24-hour window."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_id,
            "type": "text",
            "text": {"preview_url": preview_url, "body": body[:4096]},
        }
        return await self._send(payload, wa_id=wa_id, kind="text")

    async def send_image(self, wa_id: str, image_url: str, *, caption: str = "") -> str:
        """Send an image by public URL. Only legal inside the 24-hour window.

        Meta fetches the URL itself, so nothing is uploaded here — but that also
        means a URL Meta cannot reach fails the send rather than degrading to a
        broken image. The caption is what the customer reads under the photo.
        """
        image: dict[str, Any] = {"link": image_url}
        if caption:
            image["caption"] = caption[:1024]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_id,
            "type": "image",
            "image": image,
        }
        return await self._send(payload, wa_id=wa_id, kind="image")

    async def send_template(
        self,
        wa_id: str,
        template_name: str,
        *,
        language: str = "en",
        variables: Iterable[Any] = (),
    ) -> str:
        """Send an approved template. Legal at any time."""
        parameters = [{"type": "text", "text": str(v)} for v in variables]
        components = [{"type": "body", "parameters": parameters}] if parameters else []
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_id,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                **({"components": components} if components else {}),
            },
        }
        return await self._send(payload, wa_id=wa_id, kind=f"template:{template_name}")

    async def mark_read(self, wa_message_id: str) -> None:
        """Best-effort read receipt. A failure here must never break a reply."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wa_message_id,
        }
        try:
            await self._post(f"{self._phone_number_id}/messages", payload)
        except Exception as exc:
            log.debug("mark_read failed", extra={"wa_message_id": wa_message_id, "error": str(exc)})

    async def _send(self, payload: dict[str, Any], *, wa_id: str, kind: str) -> str:
        try:
            data = await self._post(f"{self._phone_number_id}/messages", payload)
        except WhatsAppError as exc:
            log.error(
                "whatsapp send failed",
                extra={"wa_id": wa_id, "kind": kind, "code": exc.code, "error": str(exc)},
            )
            raise
        except _Retryable as exc:
            log.error("whatsapp send failed after retries",
                      extra={"wa_id": wa_id, "kind": kind, "error": str(exc)})
            raise WhatsAppError(str(exc)) from exc

        message_id = ""
        messages = data.get("messages") if isinstance(data, dict) else None
        if isinstance(messages, list) and messages:
            message_id = str(messages[0].get("id") or "")

        log.info(
            "whatsapp send ok",
            extra={"wa_id": wa_id, "kind": kind, "wa_message_id": message_id},
        )
        return message_id

    # -- media -------------------------------------------------------------
    async def media_info(self, media_id: str) -> dict[str, Any] | None:
        """Resolve Meta's short-lived download URL and media metadata."""
        try:
            response = await self._client.get(f"{self._base}/{media_id}")
            response.raise_for_status()
            return _safe_json(response)
        except httpx.HTTPError as exc:
            log.warning("media lookup failed", extra={"media_id": media_id, "error": str(exc)})
            return None

    async def media_url(self, media_id: str) -> str | None:
        info = await self.media_info(media_id)
        return str(info.get("url")) if info and info.get("url") else None

    async def download_media(self, media_id: str, *, max_bytes: int) -> DownloadedMedia:
        """Download one Meta attachment with authentication and a hard size cap."""
        info = await self.media_info(media_id)
        if not info or not info.get("url"):
            raise WhatsAppError("WhatsApp media URL could not be resolved")

        declared_size = info.get("file_size")
        try:
            if declared_size is not None and int(declared_size) > max_bytes:
                raise WhatsAppError(f"WhatsApp media exceeds the {max_bytes}-byte limit")
        except (TypeError, ValueError):
            pass

        chunks: list[bytes] = []
        received = 0
        content_type = ""
        try:
            async with self._client.stream("GET", str(info["url"])) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type") or ""
                content_length = response.headers.get("content-length")
                try:
                    if content_length and int(content_length) > max_bytes:
                        raise WhatsAppError(
                            f"WhatsApp media exceeds the {max_bytes}-byte limit"
                        )
                except (TypeError, ValueError):
                    # Some proxies return a malformed Content-Length. The
                    # streaming counter below remains the authoritative cap.
                    pass
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > max_bytes:
                        raise WhatsAppError(f"WhatsApp media exceeds the {max_bytes}-byte limit")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise WhatsAppError("WhatsApp media download failed", details=str(exc)) from exc

        mime_type = str(
            info.get("mime_type") or content_type or "application/octet-stream"
        ).split(";", 1)[0].strip().lower()
        extension = _MEDIA_EXTENSIONS.get(mime_type, ".bin")
        return DownloadedMedia(
            content=b"".join(chunks),
            mime_type=mime_type,
            filename=f"whatsapp-{media_id}{extension}",
        )


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except ValueError:
        return {"raw": response.text[:500]}


_client: WhatsAppClient | None = None


def get_client() -> WhatsAppClient:
    global _client
    if _client is None:
        _client = WhatsAppClient()
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
