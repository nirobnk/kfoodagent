"""Image analysis sends the in-memory photo to OpenAI and reads back JSON."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from vision import ImageAnalysis, ImageAnalysisUnavailable, describe_image
from whatsapp import DownloadedMedia


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def client_returning(payload: dict | str) -> tuple[SimpleNamespace, FakeCompletions]:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    completions = FakeCompletions(content)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


PHOTO = DownloadedMedia(b"\xff\xd8jpeg", "image/jpeg", "whatsapp-1.jpg")


async def test_sends_photo_and_catalogue_and_parses_product():
    client, completions = client_returning(
        {
            "kind": "product",
            "products": ["Shin Ramyun Black"],
            "description": "  A Nongshim   Shin Black packet. ",
        }
    )

    result = await describe_image(
        PHOTO, catalogue=["Shin Ramyun Black", "Banana Milk"], client=client, model="m"
    )

    assert result == ImageAnalysis(
        kind="product", products=["Shin Ramyun Black"], description="A Nongshim Shin Black packet."
    )
    assert result.as_text() == "Product photo: Shin Ramyun Black. A Nongshim Shin Black packet."
    call = completions.calls[0]
    assert call["model"] == "m"
    assert call["response_format"] == {"type": "json_object"}
    system, user = call["messages"]
    assert "- Banana Milk" in system["content"]
    assert user["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_payment_slip_is_labelled_and_carries_no_product_names():
    client, _ = client_returning(
        {"kind": "payment_slip", "products": ["ignored"], "description": "Transfer of Rs. 1,300."}
    )

    result = await describe_image(PHOTO, client=client)

    assert result.products == []
    assert result.as_text() == "Payment slip. Transfer of Rs. 1,300."


async def test_unknown_kind_becomes_other():
    client, _ = client_returning({"kind": "selfie", "description": "A person smiling."})

    result = await describe_image(PHOTO, client=client)

    assert result.kind == "other"
    assert result.as_text() == "A person smiling."


@pytest.mark.parametrize(
    "media",
    [
        DownloadedMedia(b"", "image/jpeg", "empty.jpg"),
        DownloadedMedia(b"%PDF", "application/pdf", "slip.pdf"),
    ],
)
async def test_unusable_media_is_refused_before_any_call(media):
    client, completions = client_returning({"kind": "other", "description": "x"})

    with pytest.raises(ImageAnalysisUnavailable):
        await describe_image(media, client=client)
    assert completions.calls == []


@pytest.mark.parametrize("content", ["not json", json.dumps({"kind": "product"})])
async def test_unreadable_answer_raises(content):
    client, _ = client_returning(content)

    with pytest.raises(ImageAnalysisUnavailable):
        await describe_image(PHOTO, client=client)
