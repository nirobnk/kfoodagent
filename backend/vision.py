"""Work out what a customer's photo shows before the sales agent sees it.

Customers send a picture of a pack instead of typing its name — a screenshot
from TikTok, a photo of an empty packet, a shelf in Korea. The chat model does
not open attachments, so without this the agent can only ask "which one is
that?". Here a vision model looks at the image once, names the product in the
shop's own catalogue words where it can, and the result is kept on the message
row so staff and later agent turns read the same thing.

Image bytes live only for this call: they are not written to disk or logged.
Payment slips are recognised as slips and nothing more — no account numbers,
names or references are copied into the description.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from config import settings
from whatsapp import DownloadedMedia

# What OpenAI's vision input accepts. WhatsApp sends photos as JPEG and
# screenshots as PNG; anything else is refused rather than paid for.
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

KINDS = {"product", "payment_slip", "other"}

# The catalogue names are there to be matched against, not recited; a cap
# keeps the prompt cheap should the shelf ever grow large.
MAX_CATALOGUE_NAMES = 200

INSTRUCTIONS = """You help a Korean food shop in Sri Lanka understand photos customers send on WhatsApp.

Look at the image and answer with JSON only, in exactly this shape:
{"kind": "product" | "payment_slip" | "other",
 "products": ["..."],
 "description": "..."}

kind:
- "product": the image shows food or drink packaging, a noodle dish, a menu, or a screenshot of a product.
- "payment_slip": a bank transfer receipt, deposit slip, or banking-app payment confirmation.
- "other": anything else.

products: for "product" only. Name each distinct product you can see. If it is one of the shop's products listed below, copy that name exactly. Otherwise write the brand and product name as printed on the pack (translate Korean into the English name it is sold under, e.g. 불닭볶음면 -> "Samyang Buldak Hot Chicken Flavour Ramen"). Empty list otherwise.

description: one short English sentence a shop assistant could act on — the brand, flavour, pack type (cup / packet / bottle / multipack) and any visible count. For a payment slip say only that it is a payment slip and, if clearly printed, the amount; never copy account numbers, names or reference numbers. Do not guess what you cannot see.

The shop's products:
{catalogue}"""


class ImageAnalysisUnavailable(RuntimeError):
    """The feature is not configured or the received file cannot be used."""


@dataclass(frozen=True, slots=True)
class ImageAnalysis:
    kind: str
    description: str
    products: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        """The one line stored on the message and shown to the agent and staff."""
        if self.kind == "payment_slip":
            return f"Payment slip. {self.description}".strip()
        if self.kind == "product" and self.products:
            return f"Product photo: {', '.join(self.products)}. {self.description}".strip()
        if self.kind == "product":
            return f"Product photo. {self.description}".strip()
        return self.description


def _parse(raw: str) -> ImageAnalysis:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ImageAnalysisUnavailable("image analysis did not return JSON") from exc
    if not isinstance(data, dict):
        raise ImageAnalysisUnavailable("image analysis returned an unexpected shape")

    kind = str(data.get("kind") or "other").strip().lower()
    if kind not in KINDS:
        kind = "other"
    description = " ".join(str(data.get("description") or "").split())[:400]
    products_raw = data.get("products") if kind == "product" else []
    products = [
        " ".join(str(p).split())[:120]
        for p in (products_raw if isinstance(products_raw, list) else [])
        if str(p).strip()
    ][:5]

    if not description and not products:
        raise ImageAnalysisUnavailable("image analysis returned no description")
    return ImageAnalysis(kind=kind, description=description, products=products)


async def describe_image(
    media: DownloadedMedia,
    *,
    catalogue: Sequence[str] = (),
    client: Any | None = None,
    model: str | None = None,
) -> ImageAnalysis:
    """Describe one customer image in terms the sales agent can search with."""
    if not media.content:
        raise ImageAnalysisUnavailable("image was empty")
    if len(media.content) > settings.image_max_bytes:
        raise ImageAnalysisUnavailable("image exceeded the configured size limit")
    mime_type = media.mime_type.split(";", 1)[0].strip().lower()
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise ImageAnalysisUnavailable(f"unsupported image MIME type: {media.mime_type}")

    owned_client = client is None
    if client is None:
        api_key = settings.openai_api_key.get_secret_value()
        if not api_key:
            raise ImageAnalysisUnavailable("OPENAI_API_KEY is not configured")
        client = AsyncOpenAI(
            api_key=api_key,
            timeout=settings.image_analysis_timeout_seconds,
            max_retries=2,
        )

    names = "\n".join(f"- {name}" for name in list(catalogue)[:MAX_CATALOGUE_NAMES])
    encoded = base64.b64encode(media.content).decode("ascii")
    try:
        result = await client.chat.completions.create(
            model=model or settings.image_analysis_model,
            response_format={"type": "json_object"},
            max_tokens=300,
            messages=[
                {
                    "role": "system",
                    "content": INSTRUCTIONS.replace("{catalogue}", names or "(not available)"),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}",
                                "detail": "auto",
                            },
                        }
                    ],
                },
            ],
        )
        raw = result.choices[0].message.content if result.choices else ""
        return _parse(raw or "")
    finally:
        if owned_client:
            await client.close()
