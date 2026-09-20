"""Authenticated, size-limited WhatsApp media downloads."""

from __future__ import annotations

import httpx
import pytest

from whatsapp import WhatsAppClient, WhatsAppError


async def make_client(handler) -> WhatsAppClient:
    client = WhatsAppClient(
        access_token="secret-token",
        phone_number_id="phone-id",
        api_base="https://graph.example/v26.0",
    )
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={
            "Authorization": "Bearer secret-token",
            "Content-Type": "application/json",
        },
    )
    return client


async def test_download_media_resolves_and_downloads_with_bearer_token():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == "https://graph.example/v26.0/media-1":
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.example/audio",
                    "mime_type": "audio/ogg",
                    "file_size": 5,
                },
            )
        return httpx.Response(
            200,
            content=b"voice",
            headers={"content-type": "audio/ogg", "content-length": "5"},
        )

    client = await make_client(handler)
    try:
        media = await client.download_media("media-1", max_bytes=100)
    finally:
        await client.aclose()

    assert media.content == b"voice"
    assert media.mime_type == "audio/ogg"
    assert media.filename == "whatsapp-media-1.ogg"
    assert len(requests) == 2
    assert all(r.headers["authorization"] == "Bearer secret-token" for r in requests)


async def test_declared_oversized_media_is_rejected_before_download():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"url": "https://lookaside.example/audio", "file_size": 101},
        )

    client = await make_client(handler)
    try:
        with pytest.raises(WhatsAppError, match="exceeds"):
            await client.download_media("media-big", max_bytes=100)
    finally:
        await client.aclose()

    assert len(requests) == 1
